"""Agent configuration – loaded from env vars or /etc/cert-agent/agent.conf."""

import os
from dataclasses import dataclass, field
from pathlib import Path

# Default paths
DEFAULT_STATE_DIR = Path("/var/lib/cert-agent")
DEFAULT_NGINX_CERT_DIR = Path("/etc/nginx/certs")


@dataclass
class AgentConfig:
    # Control plane connection
    control_plane_url: str = ""          # e.g. https://cp.example.com:8443
    ca_cert_path: str = ""               # CA cert to verify server TLS

    # Bootstrap (first-run only)
    bootstrap_token: str = ""
    agent_name: str = ""                 # Must match the name pre-registered in control plane

    # Local state
    state_dir: Path = DEFAULT_STATE_DIR  # Stores key, cert, agent_id

    # nginx deployment
    nginx_cert_dir: Path = DEFAULT_NGINX_CERT_DIR
    nginx_reload_cmd: str = "nginx -s reload"

    # Heartbeat
    heartbeat_interval: int = 30         # seconds

    # Proactive renewal: renew if cert expires within N days
    renew_before_expiry_days: int = 7

    # mTLS failure tolerance: re-register after N consecutive auth failures
    max_auth_failures: int = 3

    @property
    def key_path(self) -> Path:
        return self.state_dir / "agent.key"

    @property
    def cert_path(self) -> Path:
        return self.state_dir / "agent.crt"

    @property
    def chain_path(self) -> Path:
        return self.state_dir / "ca-chain.crt"

    @property
    def agent_id_path(self) -> Path:
        return self.state_dir / "agent_id"

    # nginx target paths
    @property
    def nginx_cert_path(self) -> Path:
        return self.nginx_cert_dir / f"{self.agent_name}.crt"

    @property
    def nginx_key_path(self) -> Path:
        return self.nginx_cert_dir / f"{self.agent_name}.key"

    @property
    def nginx_chain_path(self) -> Path:
        return self.nginx_cert_dir / f"{self.agent_name}-chain.crt"

    def is_registered(self) -> bool:
        return self.agent_id_path.exists() and self.cert_path.exists()

    @classmethod
    def from_env(cls) -> "AgentConfig":
        return cls(
            control_plane_url=os.environ.get("CERT_AGENT_CP_URL", ""),
            ca_cert_path=os.environ.get("CERT_AGENT_CA_CERT", ""),
            bootstrap_token=os.environ.get("CERT_AGENT_BOOTSTRAP_TOKEN", ""),
            agent_name=os.environ.get("CERT_AGENT_NAME", ""),
            state_dir=Path(os.environ.get("CERT_AGENT_STATE_DIR", str(DEFAULT_STATE_DIR))),
            nginx_cert_dir=Path(os.environ.get("CERT_AGENT_NGINX_CERT_DIR", str(DEFAULT_NGINX_CERT_DIR))),
            nginx_reload_cmd=os.environ.get("CERT_AGENT_NGINX_RELOAD_CMD", "nginx -s reload"),
            heartbeat_interval=int(os.environ.get("CERT_AGENT_HEARTBEAT_INTERVAL", "30")),
            renew_before_expiry_days=int(os.environ.get("CERT_AGENT_RENEW_BEFORE_DAYS", "7")),
            max_auth_failures=int(os.environ.get("CERT_AGENT_MAX_AUTH_FAILURES", "3")),
        )

    def validate(self) -> list[str]:
        errors = []
        if not self.control_plane_url:
            errors.append("CERT_AGENT_CP_URL is required")
        if not self.agent_name:
            errors.append("CERT_AGENT_NAME is required")
        if not self.ca_cert_path:
            errors.append("CERT_AGENT_CA_CERT is required (path to CA cert for TLS verification)")
        if not self.is_registered() and not self.bootstrap_token:
            errors.append("CERT_AGENT_BOOTSTRAP_TOKEN is required for first-run registration")
        return errors
