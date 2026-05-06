"""Agent configuration – loaded from env vars or /etc/cert-agent/agent.conf."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

# Default paths
DEFAULT_STATE_DIR = Path("/var/lib/cert-agent")
DEFAULT_NGINX_CERT_DIR = Path("/etc/nginx/certs")


@dataclass
class AgentConfig:
    # Control plane connection
    control_plane_url: str = ""   # e.g. https://cp.example.com

    # Agent identity
    agent_name: str = ""          # Must be unique across agents

    # Auth: issued by control plane after admin approval
    # Can also be pre-configured if token is already known
    agent_token: str = ""

    # Certificate table: list of {local_path, cert_name} dicts
    # Agent reads each local_path to get current_not_after,
    # then asks the control plane whether to update.
    # Example: [{"local_path": "/etc/nginx/ssl/a.crt", "cert_name": "prod-api"}]
    cert_table: list[dict] = field(default_factory=list)

    # Local state
    state_dir: Path = DEFAULT_STATE_DIR

    # nginx deployment
    nginx_cert_dir: Path = DEFAULT_NGINX_CERT_DIR
    nginx_reload_cmd: str = "nginx -s reload"

    # Timing
    heartbeat_interval: int = 30   # seconds between heartbeats
    poll_interval: int = 5         # seconds between approval polls

    # ---------------------------------------------------------------------------
    # Derived paths
    # ---------------------------------------------------------------------------

    @property
    def key_path(self) -> Path:
        """Agent's RSA private key."""
        return self.state_dir / "agent.key"

    @property
    def pubkey_path(self) -> Path:
        """Agent's RSA public key (DER)."""
        return self.state_dir / "agent.pub"

    @property
    def agent_id_path(self) -> Path:
        return self.state_dir / "agent_id"

    @property
    def agent_token_path(self) -> Path:
        return self.state_dir / "agent_token"

    # ---------------------------------------------------------------------------
    # Status helpers
    # ---------------------------------------------------------------------------

    def is_registered(self) -> bool:
        """True if we have a persisted agent_token."""
        return self.agent_token_path.exists()

    def load_agent_token(self) -> str:
        """Load agent_token from disk (returns "" if not found)."""
        if self.agent_token_path.exists():
            return self.agent_token_path.read_text().strip()
        return self.agent_token

    def save_agent_token(self, token: str) -> None:
        self.agent_token_path.write_text(token)
        self.agent_token_path.chmod(0o600)
        self.agent_token = token

    # ---------------------------------------------------------------------------
    # Factory
    # ---------------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> "AgentConfig":
        cert_table_raw = os.environ.get("CERT_AGENT_CERT_TABLE", "[]")
        try:
            cert_table = json.loads(cert_table_raw)
        except json.JSONDecodeError:
            cert_table = []

        state_dir = Path(os.environ.get("CERT_AGENT_STATE_DIR", str(DEFAULT_STATE_DIR)))

        cfg = cls(
            control_plane_url=os.environ.get("CERT_AGENT_CP_URL", ""),
            agent_name=os.environ.get("CERT_AGENT_NAME", ""),
            agent_token=os.environ.get("CERT_AGENT_TOKEN", ""),
            cert_table=cert_table,
            state_dir=state_dir,
            nginx_cert_dir=Path(os.environ.get("CERT_AGENT_NGINX_CERT_DIR", str(DEFAULT_NGINX_CERT_DIR))),
            nginx_reload_cmd=os.environ.get("CERT_AGENT_NGINX_RELOAD_CMD", "nginx -s reload"),
            heartbeat_interval=int(os.environ.get("CERT_AGENT_HEARTBEAT_INTERVAL", "30")),
            poll_interval=int(os.environ.get("CERT_AGENT_POLL_INTERVAL", "5")),
        )
        # If token not in env, try loading from state dir
        if not cfg.agent_token:
            cfg.agent_token = cfg.load_agent_token()
        return cfg

    def validate(self) -> list[str]:
        errors = []
        if not self.control_plane_url:
            errors.append("CERT_AGENT_CP_URL is required")
        if not self.agent_name:
            errors.append("CERT_AGENT_NAME is required")
        return errors
