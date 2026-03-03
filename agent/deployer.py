"""Deploy certificates to nginx and reload."""

import logging
import shutil
import subprocess
from pathlib import Path

from agent.config import AgentConfig

logger = logging.getLogger(__name__)


def deploy_to_nginx(config: AgentConfig) -> None:
    """Copy cert/key/chain from agent state dir to nginx cert dir and reload.

    File layout after deployment:
        {nginx_cert_dir}/{agent_name}.crt       – server certificate
        {nginx_cert_dir}/{agent_name}.key       – private key (0600)
        {nginx_cert_dir}/{agent_name}-chain.crt – CA chain
    """
    config.nginx_cert_dir.mkdir(parents=True, exist_ok=True)

    # Copy cert
    _safe_copy(config.cert_path, config.nginx_cert_path, mode=0o644)

    # Copy key (restrictive permissions)
    _safe_copy(config.key_path, config.nginx_key_path, mode=0o600)

    # Copy chain
    if config.chain_path.exists():
        _safe_copy(config.chain_path, config.nginx_chain_path, mode=0o644)

    logger.info(
        "Certificates deployed to %s/{%s.crt, .key, -chain.crt}",
        config.nginx_cert_dir,
        config.agent_name,
    )

    # Reload nginx
    _reload_nginx(config.nginx_reload_cmd)


def _safe_copy(src: Path, dst: Path, mode: int) -> None:
    """Copy file with a tmp-then-rename pattern to avoid partial writes."""
    tmp = dst.with_suffix(dst.suffix + ".tmp")
    shutil.copy2(src, tmp)
    tmp.chmod(mode)
    tmp.rename(dst)


def _reload_nginx(cmd: str) -> None:
    """Execute the nginx reload command."""
    logger.info("Reloading nginx: %s", cmd)
    try:
        result = subprocess.run(
            cmd.split(),
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            logger.error("nginx reload failed (rc=%d): %s", result.returncode, result.stderr)
        else:
            logger.info("nginx reloaded successfully")
    except subprocess.TimeoutExpired:
        logger.error("nginx reload timed out")
    except FileNotFoundError:
        logger.error("nginx binary not found: %s", cmd)
