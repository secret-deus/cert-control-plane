"""HTTP client for the control plane Agent API.

Uses httpx with mTLS (client cert + CA verification).
"""

import logging

import httpx

from agent.config import AgentConfig

logger = logging.getLogger(__name__)


class ControlPlaneClient:
    """Thin wrapper around the /api/agent/* endpoints."""

    def __init__(self, config: AgentConfig) -> None:
        self._config = config
        self._base = config.control_plane_url.rstrip("/")

    # ------------------------------------------------------------------
    # Internal: build httpx client
    # ------------------------------------------------------------------

    def _make_client(self, *, use_client_cert: bool = True) -> httpx.Client:
        """Create a synchronous httpx client.

        use_client_cert=True  → mTLS (for bundle/renew/heartbeat)
        use_client_cert=False → no client cert (for bootstrap register)
        """
        kwargs: dict = {
            "verify": self._config.ca_cert_path,
            "timeout": 30.0,
        }
        if use_client_cert and self._config.cert_path.exists():
            kwargs["cert"] = (
                str(self._config.cert_path),
                str(self._config.key_path),
            )
        return httpx.Client(**kwargs)

    # ------------------------------------------------------------------
    # POST /api/agent/register
    # ------------------------------------------------------------------

    def register(self, csr_pem: str) -> dict:
        """Bootstrap registration. Returns {cert_pem, chain_pem, agent_id}."""
        url = f"{self._base}/api/agent/register"
        with self._make_client(use_client_cert=False) as client:
            resp = client.post(url, json={
                "bootstrap_token": self._config.bootstrap_token,
                "csr_pem": csr_pem,
            })
            resp.raise_for_status()
            return resp.json()

    # ------------------------------------------------------------------
    # POST /api/agent/heartbeat
    # ------------------------------------------------------------------

    def heartbeat(self) -> dict:
        """Send heartbeat. Returns {acknowledged, pending_action}."""
        url = f"{self._base}/api/agent/heartbeat"
        with self._make_client() as client:
            resp = client.post(url, json={"status": "ok"})
            resp.raise_for_status()
            return resp.json()

    # ------------------------------------------------------------------
    # POST /api/agent/renew
    # ------------------------------------------------------------------

    def renew(self, csr_pem: str) -> dict:
        """Submit a new CSR for cert renewal. Returns {cert_pem, chain_pem, serial_hex}."""
        url = f"{self._base}/api/agent/renew"
        with self._make_client() as client:
            resp = client.post(url, json={"csr_pem": csr_pem})
            resp.raise_for_status()
            return resp.json()

    # ------------------------------------------------------------------
    # GET /api/agent/bundle
    # ------------------------------------------------------------------

    def download_bundle(self) -> str:
        """Download the current PEM bundle."""
        url = f"{self._base}/api/agent/bundle"
        with self._make_client() as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.text
