"""Tests for Kubernetes TLS Secret planning helpers."""

import base64
from datetime import datetime, timedelta, timezone

import pytest
import yaml
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app.services.kubernetes_secrets import (
    KubeconfigError,
    build_secret_merge_patch,
    build_tls_secret_body,
    parse_service_account_kubeconfig,
    verify_certificate_key_pair,
)


def _service_account_kubeconfig() -> str:
    data = {
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
            {
                "name": "cert-control-plane",
                "user": {"token": "sa-token-value"},
            }
        ],
        "contexts": [
            {
                "name": "minikube-sa",
                "context": {
                    "cluster": "minikube",
                    "user": "cert-control-plane",
                    "namespace": "cert-system",
                },
            }
        ],
    }
    return yaml.safe_dump(data)


def _exec_kubeconfig() -> str:
    data = yaml.safe_load(_service_account_kubeconfig())
    data["users"][0]["user"] = {"exec": {"command": "kubelogin"}}
    return yaml.safe_dump(data)


def _cert_and_key(common_name: str = "api.example.com") -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(tz=timezone.utc)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()
    return cert_pem, key_pem


def test_parse_service_account_kubeconfig_accepts_static_token():
    parsed = parse_service_account_kubeconfig(_service_account_kubeconfig())

    assert parsed.api_server == "https://127.0.0.1:8443"
    assert parsed.token == "sa-token-value"
    assert parsed.default_namespace == "cert-system"
    assert parsed.context_name == "minikube-sa"
    assert parsed.ca_cert_pem.startswith("-----BEGIN CERTIFICATE-----")


def test_parse_service_account_kubeconfig_rejects_exec_auth():
    with pytest.raises(KubeconfigError, match="dynamic authentication"):
        parse_service_account_kubeconfig(_exec_kubeconfig())


def test_verify_certificate_key_pair_accepts_matching_material():
    cert_pem, key_pem = _cert_and_key()

    result = verify_certificate_key_pair(cert_pem, key_pem)

    assert result.serial_hex
    assert result.subject_cn == "api.example.com"


def test_build_tls_secret_body_writes_fullchain_and_annotations():
    cert_pem, key_pem = _cert_and_key()
    chain_pem, _ = _cert_and_key("chain.example.com")

    body = build_tls_secret_body(
        namespace="default",
        secret_name="api-tls",
        cert_pem=cert_pem,
        key_pem=key_pem,
        chain_pem=chain_pem,
        assignment_id="assignment-1",
        external_cert_id="cert-1",
        serial_hex="abc123",
    )

    assert body["type"] == "kubernetes.io/tls"
    assert body["metadata"]["name"] == "api-tls"
    assert body["metadata"]["namespace"] == "default"
    assert body["metadata"]["annotations"]["cert-control-plane.io/serial"] == "abc123"
    assert base64.b64decode(body["data"]["tls.crt"]).decode() == cert_pem + chain_pem
    assert base64.b64decode(body["data"]["tls.key"]).decode() == key_pem


def test_build_secret_merge_patch_only_sets_tls_fields_and_platform_annotations():
    cert_pem, key_pem = _cert_and_key()

    patch = build_secret_merge_patch(
        cert_pem=cert_pem,
        key_pem=key_pem,
        chain_pem=None,
        assignment_id="assignment-1",
        external_cert_id="cert-1",
        serial_hex="abc123",
    )

    assert set(patch.keys()) == {"type", "data", "metadata"}
    assert set(patch["data"].keys()) == {"tls.crt", "tls.key"}
    assert list(patch["metadata"].keys()) == ["annotations"]
    assert patch["metadata"]["annotations"]["cert-control-plane.io/assignment-id"] == "assignment-1"
