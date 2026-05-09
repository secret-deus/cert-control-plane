"""Kubernetes TLS Secret helpers and low-level API client."""

from __future__ import annotations

import base64
import json
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
import yaml
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import NameOID


class KubeconfigError(ValueError):
    """Raised when an uploaded kubeconfig is not acceptable for server-side use."""


class KubernetesApiError(RuntimeError):
    """Raised when the Kubernetes API returns an unexpected response."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ParsedServiceAccountKubeconfig:
    api_server: str
    token: str
    ca_cert_pem: str
    default_namespace: str | None
    context_name: str


@dataclass(frozen=True)
class CertificateKeyPairResult:
    subject_cn: str
    serial_hex: str
    not_before: datetime
    not_after: datetime


def parse_service_account_kubeconfig(
    kubeconfig_text: str,
    *,
    context_name: str | None = None,
) -> ParsedServiceAccountKubeconfig:
    """Parse a static ServiceAccount token kubeconfig.

    V1 intentionally rejects dynamic kubeconfig auth such as exec/auth-provider
    because the control plane must not depend on kubectl plugins or cloud CLIs.
    """

    try:
        data = yaml.safe_load(kubeconfig_text)
    except yaml.YAMLError as exc:
        raise KubeconfigError(f"Invalid kubeconfig YAML: {exc}") from exc

    if not isinstance(data, dict):
        raise KubeconfigError("Invalid kubeconfig: expected mapping")

    contexts = {item.get("name"): item.get("context", {}) for item in data.get("contexts", [])}
    clusters = {item.get("name"): item.get("cluster", {}) for item in data.get("clusters", [])}
    users = {item.get("name"): item.get("user", {}) for item in data.get("users", [])}

    selected_context_name = context_name or data.get("current-context")
    if not selected_context_name or selected_context_name not in contexts:
        raise KubeconfigError("Invalid kubeconfig: current context not found")

    context = contexts[selected_context_name]
    cluster = clusters.get(context.get("cluster"))
    user = users.get(context.get("user"))
    if not cluster or not user:
        raise KubeconfigError("Invalid kubeconfig: context cluster/user not found")

    if any(key in user for key in ("exec", "auth-provider", "auth_provider")):
        raise KubeconfigError("V1 does not support dynamic authentication in kubeconfig")

    token = user.get("token")
    if not token:
        raise KubeconfigError("V1 requires a ServiceAccount token kubeconfig")

    api_server = cluster.get("server")
    if not api_server:
        raise KubeconfigError("Invalid kubeconfig: cluster server is required")

    ca_cert_pem = _load_ca_cert(cluster)

    namespace = context.get("namespace")
    return ParsedServiceAccountKubeconfig(
        api_server=api_server,
        token=token,
        ca_cert_pem=ca_cert_pem,
        default_namespace=namespace,
        context_name=selected_context_name,
    )


def verify_certificate_key_pair(cert_pem: str, key_pem: str) -> CertificateKeyPairResult:
    cert = x509.load_pem_x509_certificate(cert_pem.encode())
    key = serialization.load_pem_private_key(key_pem.encode(), password=None)

    cert_public = cert.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    key_public = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    if cert_public != key_public:
        raise ValueError("Certificate and private key do not match")

    cn_attrs = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    if not cn_attrs:
        raise ValueError("Certificate missing Common Name")

    return CertificateKeyPairResult(
        subject_cn=cn_attrs[0].value,
        serial_hex=format(cert.serial_number, "x").lower(),
        not_before=cert.not_valid_before_utc,
        not_after=cert.not_valid_after_utc,
    )


def build_tls_secret_body(
    *,
    namespace: str,
    secret_name: str,
    cert_pem: str,
    key_pem: str,
    chain_pem: str | None,
    assignment_id: str,
    external_cert_id: str,
    serial_hex: str,
) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": secret_name,
            "namespace": namespace,
            "annotations": _deploy_annotations(
                assignment_id=assignment_id,
                external_cert_id=external_cert_id,
                serial_hex=serial_hex,
            ),
        },
        "type": "kubernetes.io/tls",
        "data": _tls_data(cert_pem=cert_pem, key_pem=key_pem, chain_pem=chain_pem),
    }


def build_secret_merge_patch(
    *,
    cert_pem: str,
    key_pem: str,
    chain_pem: str | None,
    assignment_id: str,
    external_cert_id: str,
    serial_hex: str,
) -> dict[str, Any]:
    return {
        "type": "kubernetes.io/tls",
        "data": _tls_data(cert_pem=cert_pem, key_pem=key_pem, chain_pem=chain_pem),
        "metadata": {
            "annotations": _deploy_annotations(
                assignment_id=assignment_id,
                external_cert_id=external_cert_id,
                serial_hex=serial_hex,
            )
        },
    }


def build_adopt_patch(*, assignment_id: str, current_serial_hex: str | None) -> dict[str, Any]:
    now = datetime.now(tz=timezone.utc).isoformat()
    annotations = {
        "cert-control-plane.io/managed": "true",
        "cert-control-plane.io/assignment-id": assignment_id,
        "cert-control-plane.io/adopted-at": now,
    }
    if current_serial_hex:
        annotations["cert-control-plane.io/adopted-serial"] = current_serial_hex
    return {"metadata": {"annotations": annotations}}


def build_rollback_patch(
    *,
    cert_pem: str,
    key_pem: str,
    chain_pem: str | None,
    assignment_id: str,
    operation_id: str,
    serial_hex: str,
) -> dict[str, Any]:
    now = datetime.now(tz=timezone.utc).isoformat()
    return {
        "data": _tls_data(cert_pem=cert_pem, key_pem=key_pem, chain_pem=chain_pem),
        "metadata": {
            "annotations": {
                "cert-control-plane.io/managed": "true",
                "cert-control-plane.io/assignment-id": assignment_id,
                "cert-control-plane.io/serial": serial_hex,
                "cert-control-plane.io/rolled-back-at": now,
                "cert-control-plane.io/operation-id": operation_id,
            }
        },
    }


def extract_secret_resource_version(secret: dict[str, Any] | None) -> str | None:
    if not secret:
        return None
    metadata = secret.get("metadata") or {}
    return metadata.get("resourceVersion")


def extract_secret_serial(secret: dict[str, Any]) -> str | None:
    data = secret.get("data") or {}
    encoded_cert = data.get("tls.crt")
    if not encoded_cert:
        return None
    cert_text = base64.b64decode(encoded_cert).decode()
    cert = x509.load_pem_x509_certificate(cert_text.encode())
    return format(cert.serial_number, "x").lower()


def is_platform_managed(secret: dict[str, Any], assignment_id: str) -> bool:
    annotations = (secret.get("metadata") or {}).get("annotations") or {}
    return (
        annotations.get("cert-control-plane.io/managed") == "true"
        and annotations.get("cert-control-plane.io/assignment-id") == assignment_id
    )


def summarize_tls_diff(
    *,
    current_secret: dict[str, Any] | None,
    target_serial_hex: str,
    target_resource_version: str | None,
) -> list[dict[str, Any]]:
    current_serial = None
    if current_secret:
        try:
            current_serial = extract_secret_serial(current_secret)
        except Exception:
            current_serial = "unparseable"
    return [
        {
            "path": "data.tls.crt",
            "before": current_serial,
            "after": target_serial_hex,
            "sensitive": False,
        },
        {
            "path": "data.tls.key",
            "before": "present" if current_secret else None,
            "after": "updated",
            "sensitive": True,
        },
        {
            "path": "metadata.resourceVersion",
            "before": target_resource_version,
            "after": "checked-at-confirm",
            "sensitive": False,
        },
    ]


class KubernetesApiClient:
    """Small async Kubernetes CoreV1 client for ServiceAccount token kubeconfigs."""

    def __init__(self, parsed: ParsedServiceAccountKubeconfig, *, timeout: float = 15.0):
        self.parsed = parsed
        self.timeout = timeout

    async def get_version(self) -> dict[str, Any]:
        return await self._request("GET", "/version")

    async def get_namespace(self, namespace: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/v1/namespaces/{namespace}")

    async def get_secret(self, namespace: str, secret_name: str) -> dict[str, Any] | None:
        try:
            return await self._request("GET", f"/api/v1/namespaces/{namespace}/secrets/{secret_name}")
        except KubernetesApiError as exc:
            if exc.status_code == 404:
                return None
            raise

    async def create_secret(self, namespace: str, body: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", f"/api/v1/namespaces/{namespace}/secrets", json_body=body)

    async def patch_secret(
        self,
        namespace: str,
        secret_name: str,
        patch: dict[str, Any],
    ) -> dict[str, Any]:
        return await self._request(
            "PATCH",
            f"/api/v1/namespaces/{namespace}/secrets/{secret_name}",
            json_body=patch,
            content_type="application/merge-patch+json",
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        content_type: str = "application/json",
    ) -> dict[str, Any]:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8") as ca_file:
            ca_file.write(self.parsed.ca_cert_pem)
            ca_file.flush()
            async with httpx.AsyncClient(
                base_url=self.parsed.api_server,
                verify=ca_file.name,
                timeout=self.timeout,
                headers={
                    "Authorization": f"Bearer {self.parsed.token}",
                    "Accept": "application/json",
                    "Content-Type": content_type,
                },
            ) as client:
                response = await client.request(method, path, json=json_body)
        if response.status_code >= 400:
            message = response.text
            try:
                payload = response.json()
                message = payload.get("message") or payload.get("reason") or message
            except ValueError:
                pass
            raise KubernetesApiError(response.status_code, message)
        if not response.content:
            return {}
        return response.json()


def encode_snapshot(snapshot: dict[str, Any]) -> bytes:
    return json.dumps(snapshot, sort_keys=True).encode()


def decode_snapshot(snapshot_bytes: bytes) -> dict[str, Any]:
    return json.loads(snapshot_bytes.decode())


def _load_ca_cert(cluster: dict[str, Any]) -> str:
    if "certificate-authority-data" in cluster:
        try:
            return base64.b64decode(cluster["certificate-authority-data"]).decode()
        except Exception as exc:
            raise KubeconfigError("Invalid kubeconfig: certificate-authority-data is not valid base64") from exc
    raise KubeconfigError("V1 requires certificate-authority-data in kubeconfig")


def _fullchain(cert_pem: str, chain_pem: str | None) -> str:
    cert = cert_pem.strip() + "\n"
    if not chain_pem:
        return cert
    return cert + chain_pem.strip() + "\n"


def _tls_data(*, cert_pem: str, key_pem: str, chain_pem: str | None) -> dict[str, str]:
    return {
        "tls.crt": base64.b64encode(_fullchain(cert_pem, chain_pem).encode()).decode(),
        "tls.key": base64.b64encode(key_pem.encode()).decode(),
    }


def _deploy_annotations(
    *,
    assignment_id: str,
    external_cert_id: str,
    serial_hex: str,
) -> dict[str, str]:
    now = datetime.now(tz=timezone.utc).isoformat()
    return {
        "cert-control-plane.io/managed": "true",
        "cert-control-plane.io/assignment-id": assignment_id,
        "cert-control-plane.io/external-cert-id": external_cert_id,
        "cert-control-plane.io/serial": serial_hex,
        "cert-control-plane.io/updated-at": now,
    }
