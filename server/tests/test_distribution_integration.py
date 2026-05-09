"""Integration tests for the external certificate distribution flow.

These tests use a real SQLite database session instead of pure AsyncMock-based
fixtures so the main upload -> assign -> fetch-certs chain is exercised end to end.
"""

import os
import uuid
import base64
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from cryptography import x509
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.database import Base, get_db
from app.main import create_app
from app.models import (
    Agent,
    AgentCertAssignment,
    AgentStatus,
    Certificate,
    KubernetesSecretAssignment,
    KubernetesSecretHealthStatus,
    KubernetesSecretOperation,
    KubernetesSecretOperationAction,
    Rollout,
    RolloutItem,
    RolloutItemStatus,
    RolloutStatus,
)


def _generate_test_certificate(common_name: str) -> tuple[str, str]:
    """Return (cert_pem, key_pem) for a short-lived self-signed certificate."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, common_name)]
    )
    now = datetime.now(tz=timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    return cert_pem, key_pem


def _service_account_kubeconfig(namespace: str = "default") -> str:
    return yaml.safe_dump(
        {
            "apiVersion": "v1",
            "kind": "Config",
            "current-context": "minikube-sa",
            "clusters": [
                {
                    "name": "minikube",
                    "cluster": {
                        "server": "https://127.0.0.1:8443",
                        "certificate-authority-data": base64.b64encode(
                            b"-----BEGIN CERTIFICATE-----\nCA\n-----END CERTIFICATE-----\n"
                        ).decode(),
                    },
                }
            ],
            "users": [
                {"name": "cert-control-plane", "user": {"token": "sa-token-value"}}
            ],
            "contexts": [
                {
                    "name": "minikube-sa",
                    "context": {
                        "cluster": "minikube",
                        "user": "cert-control-plane",
                        "namespace": namespace,
                    },
                }
            ],
        }
    )


@pytest.fixture()
async def integration_client(tmp_path: Path):
    """App client backed by a real SQLite database."""
    os.environ["CA_KEY_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    get_settings.cache_clear()

    db_path = tmp_path / "distribution-test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    app = create_app()

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers["X-Admin-API-Key"] = "test-admin-key-for-pytest"
        yield client, session_factory

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_external_cert_distribution_flow(integration_client):
    """Upload an external cert, assign it, then fetch it from the agent side."""
    client, session_factory = integration_client
    agent_name = "integration-agent-01"
    fingerprint = "a" * 64
    local_path = "/etc/nginx/certs/api.example.com.crt"

    register_resp = await client.post(
        "/api/agent/register",
        json={"name": agent_name, "fingerprint": fingerprint},
    )
    assert register_resp.status_code == 200
    register_data = register_resp.json()
    assert register_data["status"] == "pending"
    agent_id = uuid.UUID(register_data["agent_id"])

    approve_resp = await client.post(f"/api/control/agents/{agent_id}/approve")
    assert approve_resp.status_code == 200

    async with session_factory() as session:
        agent = await session.get(Agent, agent_id)
        assert agent is not None
        assert agent.status == AgentStatus.ACTIVE
        assert agent.agent_token
        agent_token = agent.agent_token

    cert_pem, key_pem = _generate_test_certificate("api.example.com")
    upload_resp = await client.post(
        "/api/control/external-certs",
        json={
            "name": "api-example-com",
            "description": "integration test cert",
            "cert_pem": cert_pem,
            "key_pem": key_pem,
            "chain_pem": None,
            "provider": "manual",
            "external_id": "integration-001",
        },
    )
    assert upload_resp.status_code == 201
    cert_id = upload_resp.json()["id"]

    assign_resp = await client.post(
        f"/api/control/agents/{agent_id}/assign-cert",
        json={
            "external_cert_id": cert_id,
            "local_path": local_path,
        },
    )
    assert assign_resp.status_code == 201
    assert assign_resp.json()["local_path"] == local_path

    fetch_resp = await client.post(
        "/api/agent/fetch-certs",
        headers={"X-Agent-Token": agent_token},
        json={
            "certs": [
                {
                    "local_path": local_path,
                    "current_not_after": None,
                }
            ]
        },
    )
    assert fetch_resp.status_code == 200
    fetch_data = fetch_resp.json()
    assert len(fetch_data["updates"]) == 1

    first_update = fetch_data["updates"][0]
    assert first_update["has_update"] is True
    assert first_update["cert_pem"] == cert_pem
    assert first_update["key_pem"] == key_pem
    assert first_update["not_after"] is not None

    second_fetch_resp = await client.post(
        "/api/agent/fetch-certs",
        headers={"X-Agent-Token": agent_token},
        json={
            "certs": [
                {
                    "local_path": local_path,
                    "current_not_after": first_update["not_after"],
                }
            ]
        },
    )
    assert second_fetch_resp.status_code == 200
    second_update = second_fetch_resp.json()["updates"][0]
    assert second_update["has_update"] is False
    assert second_update["not_after"] == first_update["not_after"]


@pytest.mark.asyncio
async def test_kubernetes_cluster_credential_update_validates_assignments(integration_client):
    """Updating a cluster kubeconfig triggers read-only validate for active K8s assignments."""
    client, session_factory = integration_client
    cert_pem, key_pem = _generate_test_certificate("k8s-update.example.com")

    upload_resp = await client.post(
        "/api/control/external-certs",
        json={
            "name": "k8s-update-example-com",
            "description": "k8s credential update validation test",
            "cert_pem": cert_pem,
            "key_pem": key_pem,
            "chain_pem": None,
            "provider": "manual",
            "external_id": "k8s-update-001",
        },
    )
    assert upload_resp.status_code == 201
    cert_id = upload_resp.json()["id"]

    cluster_resp = await client.post(
        "/api/control/kubernetes/clusters",
        json={
            "name": "minikube-test",
            "environment": "test",
            "kubeconfig": _service_account_kubeconfig("cert-system"),
        },
    )
    assert cluster_resp.status_code == 201
    cluster_id = cluster_resp.json()["id"]

    assignment_resp = await client.post(
        "/api/control/kubernetes/assignments",
        json={
            "cluster_id": cluster_id,
            "namespace": "cert-system",
            "secret_name": "api-tls",
            "external_cert_id": cert_id,
        },
    )
    assert assignment_resp.status_code == 201
    assignment_id = assignment_resp.json()["id"]

    secret = {
        "metadata": {
            "resourceVersion": "rv-after-credential-update",
            "annotations": {
                "cert-control-plane.io/managed": "true",
                "cert-control-plane.io/assignment-id": assignment_id,
            },
        },
        "data": {
            "tls.crt": base64.b64encode(cert_pem.encode()).decode(),
        },
    }

    class FakeKubernetesClient:
        async def get_secret(self, namespace: str, secret_name: str):
            assert namespace == "cert-system"
            assert secret_name == "api-tls"
            return secret

    with patch("app.api.control._kubernetes_client_from_cluster", return_value=FakeKubernetesClient()):
        update_resp = await client.put(
            f"/api/control/kubernetes/clusters/{cluster_id}/credentials",
            json={
                "kubeconfig": _service_account_kubeconfig("cert-system"),
                "default_namespace": "cert-system",
            },
        )

    assert update_resp.status_code == 200

    async with session_factory() as session:
        assignment = await session.get(KubernetesSecretAssignment, uuid.UUID(assignment_id))
        assert assignment is not None
        assert assignment.health_status == KubernetesSecretHealthStatus.HEALTHY
        assert assignment.current_resource_version == "rv-after-credential-update"
        assert assignment.last_validated_at is not None

        result = await session.execute(
            select(KubernetesSecretOperation).where(
                KubernetesSecretOperation.assignment_id == assignment.id,
                KubernetesSecretOperation.action == KubernetesSecretOperationAction.VALIDATE,
            )
        )
        operations = result.scalars().all()
        assert len(operations) == 1
        assert operations[0].serial_after == assignment.current_serial_hex


@pytest.mark.asyncio
async def test_kubernetes_cluster_and_secret_assignment_flow(integration_client):
    """Create a K8s cluster target and map one uploaded cert to one Secret."""
    client, _session_factory = integration_client

    cluster_resp = await client.post(
        "/api/control/kubernetes/clusters",
        json={
            "name": "minikube-dev",
            "environment": "dev",
            "kubeconfig": _service_account_kubeconfig("default"),
        },
    )
    assert cluster_resp.status_code == 201
    cluster = cluster_resp.json()
    assert cluster["api_server"] == "https://127.0.0.1:8443"
    assert cluster["default_namespace"] == "default"
    assert cluster["connection_status"] == "unknown"

    cert_pem, key_pem = _generate_test_certificate("api.example.com")
    upload_resp = await client.post(
        "/api/control/external-certs",
        json={
            "name": "api-example-com",
            "description": "k8s assignment test cert",
            "cert_pem": cert_pem,
            "key_pem": key_pem,
            "chain_pem": None,
            "provider": "manual",
            "external_id": "k8s-001",
        },
    )
    assert upload_resp.status_code == 201
    cert_id = upload_resp.json()["id"]

    assignment_resp = await client.post(
        "/api/control/kubernetes/assignments",
        json={
            "cluster_id": cluster["id"],
            "namespace": "default",
            "secret_name": "api-tls",
            "external_cert_id": cert_id,
        },
    )
    assert assignment_resp.status_code == 201
    assignment = assignment_resp.json()
    assert assignment["cluster_name"] == "minikube-dev"
    assert assignment["external_cert_subject_cn"] == "api.example.com"
    assert assignment["lifecycle_status"] == "pending"
    assert assignment["health_status"] == "unknown"

    list_resp = await client.get("/api/control/kubernetes/assignments")
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] == 1
    assert list_resp.json()["items"][0]["secret_name"] == "api-tls"


@pytest.mark.asyncio
async def test_rollout_gates_updates_and_records_deployment(integration_client):
    """Only in-progress agents may fetch updates, and confirmation creates cert history."""
    client, session_factory = integration_client
    local_path = "/etc/nginx/certs/rollout.example.com.crt"

    cert_pem, key_pem = _generate_test_certificate("rollout.example.com")
    upload_resp = await client.post(
        "/api/control/external-certs",
        json={
            "name": "rollout-example-com",
            "description": "rollout gate test",
            "cert_pem": cert_pem,
            "key_pem": key_pem,
            "chain_pem": None,
            "provider": "manual",
            "external_id": "rollout-001",
        },
    )
    assert upload_resp.status_code == 201
    cert_id = uuid.UUID(upload_resp.json()["id"])

    agent1_id = uuid.uuid4()
    agent2_id = uuid.uuid4()
    token1 = "rollout-token-1"
    token2 = "rollout-token-2"

    async with session_factory() as session:
        session.add_all([
            Agent(
                id=agent1_id,
                name="rollout-agent-1",
                status=AgentStatus.ACTIVE,
                fingerprint="1" * 64,
                agent_token=token1,
            ),
            Agent(
                id=agent2_id,
                name="rollout-agent-2",
                status=AgentStatus.ACTIVE,
                fingerprint="2" * 64,
                agent_token=token2,
            ),
        ])
        await session.flush()

        session.add_all([
            AgentCertAssignment(
                agent_id=agent1_id,
                external_cert_id=cert_id,
                local_path=local_path,
            ),
            AgentCertAssignment(
                agent_id=agent2_id,
                external_cert_id=cert_id,
                local_path=local_path,
            ),
        ])

        rollout = Rollout(
            name="integration-rollout",
            status=RolloutStatus.RUNNING,
            batch_size=1,
            current_batch=1,
            total_batches=2,
            created_by="admin",
        )
        session.add(rollout)
        await session.flush()

        item1 = RolloutItem(
            rollout_id=rollout.id,
            agent_id=agent1_id,
            status=RolloutItemStatus.IN_PROGRESS,
            batch_number=1,
        )
        item2 = RolloutItem(
            rollout_id=rollout.id,
            agent_id=agent2_id,
            status=RolloutItemStatus.PENDING,
            batch_number=2,
        )
        session.add_all([item1, item2])
        await session.commit()

        item1_id = item1.id
        item2_id = item2.id

    blocked_resp = await client.post(
        "/api/agent/fetch-certs",
        headers={"X-Agent-Token": token2},
        json={"certs": [{"local_path": local_path, "current_not_after": None}]},
    )
    assert blocked_resp.status_code == 200
    assert blocked_resp.json()["updates"][0]["has_update"] is False

    first_fetch_resp = await client.post(
        "/api/agent/fetch-certs",
        headers={"X-Agent-Token": token1},
        json={"certs": [{"local_path": local_path, "current_not_after": None}]},
    )
    assert first_fetch_resp.status_code == 200
    first_update = first_fetch_resp.json()["updates"][0]
    assert first_update["has_update"] is True

    confirm_resp = await client.post(
        "/api/agent/fetch-certs",
        headers={"X-Agent-Token": token1},
        json={
            "certs": [
                {
                    "local_path": local_path,
                    "current_not_after": first_update["not_after"],
                }
            ]
        },
    )
    assert confirm_resp.status_code == 200
    assert confirm_resp.json()["updates"][0]["has_update"] is False

    async with session_factory() as session:
        certs = (
            await session.execute(
                select(Certificate).where(Certificate.agent_id == agent1_id)
            )
        ).scalars().all()
        assert len(certs) == 1
        assert certs[0].local_path == local_path
        assert certs[0].is_current is True
        assert certs[0].external_cert_id == cert_id

        item1 = await session.get(RolloutItem, item1_id)
        item2 = await session.get(RolloutItem, item2_id)
        assert item1 is not None
        assert item1.status == RolloutItemStatus.COMPLETED
        assert item1.new_cert_id == certs[0].id
        assert item2 is not None
        assert item2.status == RolloutItemStatus.PENDING
