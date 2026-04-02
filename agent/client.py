"""HTTP client for the control plane Agent API.

Uses httpx without mTLS – authentication is via X-Agent-Token header.
"""

import logging
from datetime import datetime

import httpx

from agent.config import AgentConfig

logger = logging.getLogger(__name__)


class ControlPlaneClient:
    """Thin wrapper around the /api/agent/* endpoints."""

    def __init__(self, config: AgentConfig) -> None:
        self._config = config
        self._base = config.control_plane_url.rstrip("/")

    def _headers(self) -> dict:
        """Build auth headers. Empty if no token (registration phase)."""
        if self._config.agent_token:
            return {"X-Agent-Token": self._config.agent_token}
        return {}

    def _make_client(self) -> httpx.Client:
        """Create synchronous httpx client (no mTLS, plain HTTPS or HTTP)."""
        return httpx.Client(timeout=30.0)

    # ------------------------------------------------------------------
    # POST /api/agent/register  (TOFU)
    # ------------------------------------------------------------------

    def register(self, fingerprint: str) -> dict:
        """Submit TOFU registration. Returns {status, agent_id, agent_token?, message}."""
        url = f"{self._base}/api/agent/register"
        with self._make_client() as client:
            resp = client.post(url, json={
                "name": self._config.agent_name,
                "fingerprint": fingerprint,
            })
            resp.raise_for_status()
            return resp.json()

    # ------------------------------------------------------------------
    # GET /api/agent/register/status  (approval polling)
    # ------------------------------------------------------------------

    def check_registration_status(self, agent_id: str, fingerprint: str) -> dict:
        """Poll for admin approval. Returns {status, agent_token?}."""
        url = f"{self._base}/api/agent/register/status"
        with self._make_client() as client:
            resp = client.get(url, params={
                "agent_id": agent_id,
                "fingerprint": fingerprint,
            })
            resp.raise_for_status()
            return resp.json()

    # ------------------------------------------------------------------
    # POST /api/agent/heartbeat
    # ------------------------------------------------------------------

    def heartbeat(self) -> dict:
        """Send heartbeat. Returns {acknowledged}."""
        url = f"{self._base}/api/agent/heartbeat"
        with self._make_client() as client:
            resp = client.post(
                url,
                json={"status": "ok"},
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    # ------------------------------------------------------------------
    # POST /api/agent/fetch-certs  (batch)
    # ------------------------------------------------------------------

    def fetch_certs(self, cert_checks: list[dict]) -> dict:
        """Batch fetch latest certs from control plane.

        Args:
            cert_checks: list of {local_path: str, current_not_after: str | None}

        Returns:
            {updates: [{local_path, has_update, cert_pem?, key_pem?, chain_pem?, not_after?}]}
        """
        url = f"{self._base}/api/agent/fetch-certs"
        with self._make_client() as client:
            resp = client.post(
                url,
                json={"certs": cert_checks},
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    # ------------------------------------------------------------------
    # POST /api/agent/report-certs
    # ------------------------------------------------------------------

    def report_certs(self, cert_inventory: list[dict]) -> dict:
        """Report current locally deployed certificates."""
        url = f"{self._base}/api/agent/report-certs"
        with self._make_client() as client:
            resp = client.post(
                url,
                json={"certs": cert_inventory},
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()
