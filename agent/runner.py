"""Agent main loop: TOFU register → wait approval → heartbeat + fetch-certs.

Lifecycle:
  1. Generate RSA key pair (if not exists), compute fingerprint
  2. If not registered (no agent_token on disk):
     a. POST /register with {name, fingerprint}
     b. Poll /register/status until approved, save agent_token to disk
  3. Main loop (heartbeat_interval):
     a. POST /heartbeat (keeps last_seen fresh)
     b. For each entry in cert_table:
        - Read local cert file (if exists), extract not_after
        - Build batch check payload
     c. POST /fetch-certs with batch
     d. Deploy any updates (write cert/key files, reload nginx)
"""

import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from cryptography import x509

from agent.client import ControlPlaneClient
from agent.config import AgentConfig
from agent.crypto import compute_fingerprint, generate_key_pair, load_private_key
from agent.deployer import deploy_to_nginx

logger = logging.getLogger(__name__)


def run(config: AgentConfig) -> None:
    """Entry point – blocks forever."""
    config.state_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Step 1: Ensure we have a key pair
    # ------------------------------------------------------------------
    if config.key_path.exists():
        key = load_private_key(config.key_path)
        logger.info("Loaded existing private key from %s", config.key_path)
    else:
        key = generate_key_pair(config.key_path)
        logger.info("Generated new private key at %s", config.key_path)

    fingerprint = compute_fingerprint(key)
    logger.info("Agent fingerprint: %s", fingerprint)

    client = ControlPlaneClient(config)

    # ------------------------------------------------------------------
    # Step 2: Register (TOFU) if no agent_token
    # ------------------------------------------------------------------
    if not config.is_registered():
        _do_register(config, client, fingerprint)
    else:
        logger.info("Already registered, agent_token loaded from disk")

    # ------------------------------------------------------------------
    # Step 3: Main heartbeat + fetch-certs loop
    # ------------------------------------------------------------------
    logger.info(
        "Entering main loop (interval=%ds), %d cert(s) in table",
        config.heartbeat_interval,
        len(config.cert_table),
    )

    while True:
        try:
            # Heartbeat
            client.heartbeat()
            logger.debug("Heartbeat OK")

            # Fetch and deploy certs
            _do_fetch_and_deploy(config, client)

        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403):
                logger.warning(
                    "Agent token rejected (HTTP %d) – clearing token and re-registering",
                    e.response.status_code,
                )
                config.agent_token = ""
                if config.agent_token_path.exists():
                    config.agent_token_path.unlink()
                _do_register(config, client, fingerprint)
            else:
                logger.exception("HTTP error in main loop (status %d)", e.response.status_code)
        except Exception:
            logger.exception("Error in main loop, will retry")

        time.sleep(config.heartbeat_interval)


# ---------------------------------------------------------------------------
# Registration (TOFU)
# ---------------------------------------------------------------------------


def _do_register(
    config: AgentConfig,
    client: ControlPlaneClient,
    fingerprint: str,
) -> None:
    """Submit TOFU registration and poll until approved."""
    logger.info("Starting TOFU registration for '%s'", config.agent_name)

    # Submit registration
    resp = client.register(fingerprint)
    reg_status = resp.get("status")
    agent_id = resp.get("agent_id")

    logger.info("Registration response: status=%s, agent_id=%s", reg_status, agent_id)

    if reg_status == "approved" and resp.get("agent_token"):
        # Already approved (re-registration case)
        config.save_agent_token(resp["agent_token"])
        logger.info("Agent token received immediately")
        return

    if reg_status == "pending":
        # Poll until approved
        logger.info(
            "Registration pending admin approval. "
            "Polling every %ds...",
            config.poll_interval,
        )
        _poll_until_approved(config, client, agent_id, fingerprint)
        return

    raise RuntimeError(f"Unexpected registration status: {reg_status}")


def _poll_until_approved(
    config: AgentConfig,
    client: ControlPlaneClient,
    agent_id: str,
    fingerprint: str,
) -> None:
    """Block until admin approves this agent, saving agent_token when done."""
    while True:
        try:
            resp = client.check_registration_status(agent_id, fingerprint)
            poll_status = resp.get("status")

            if poll_status == "approved" and resp.get("agent_token"):
                config.save_agent_token(resp["agent_token"])
                logger.info("Admin approved! Agent token saved.")
                return

            if poll_status == "rejected":
                raise RuntimeError("Agent registration was rejected by admin")

            logger.debug("Still waiting for admin approval (status=%s)", poll_status)

        except httpx.HTTPStatusError as e:
            logger.warning("Polling failed (HTTP %d), will retry", e.response.status_code)
        except Exception:
            logger.exception("Unexpected error while polling approval, will retry")

        time.sleep(config.poll_interval)


# ---------------------------------------------------------------------------
# Fetch and deploy certificates
# ---------------------------------------------------------------------------


def _do_fetch_and_deploy(config: AgentConfig, client: ControlPlaneClient) -> None:
    """Read local cert table, ask platform for updates, deploy any changes."""
    if not config.cert_table:
        logger.debug("cert_table is empty, nothing to check")
        return

    # Build batch check payload
    cert_checks = []
    for entry in config.cert_table:
        local_path = entry.get("local_path", "")
        if not local_path:
            continue

        current_not_after = _read_cert_not_after(local_path)
        cert_checks.append({
            "local_path": local_path,
            "current_not_after": current_not_after,
        })

    if not cert_checks:
        return

    # Ask the control plane
    try:
        resp = client.fetch_certs(cert_checks)
    except Exception:
        logger.exception("Failed to fetch certs from control plane")
        return

    # Deploy updates
    for update in resp.get("updates", []):
        if not update.get("has_update"):
            continue

        local_path = update["local_path"]
        logger.info("Cert update available for %s", local_path)
        _deploy_cert_update(config, update)


def _read_cert_not_after(local_path: str) -> str | None:
    """Read a PEM cert file and return its not_after as ISO 8601 string, or None."""
    try:
        p = Path(local_path)
        if not p.exists():
            return None
        cert_pem = p.read_bytes()
        cert = x509.load_pem_x509_certificate(cert_pem)
        return cert.not_valid_after_utc.isoformat()
    except Exception:
        logger.warning("Failed to read/parse cert at %s", local_path)
        return None


def _deploy_cert_update(config: AgentConfig, update: dict) -> None:
    """Write cert+key files to local_path and reload nginx."""
    local_path = update["local_path"]
    cert_pem = update.get("cert_pem")
    key_pem = update.get("key_pem")
    chain_pem = update.get("chain_pem")

    p = Path(local_path)
    # Derive key and chain paths from cert path convention
    # e.g. /etc/nginx/ssl/api.crt → /etc/nginx/ssl/api.key
    key_path = p.with_suffix(".key")
    chain_path = p.with_suffix(".chain.crt")

    # Backup existing files
    old_cert = p.with_suffix(".crt.old")
    old_key = key_path.with_suffix(".key.old")

    if p.exists():
        _backup(p, old_cert)
    if key_path.exists():
        _backup(key_path, old_key)

    try:
        p.parent.mkdir(parents=True, exist_ok=True)

        if cert_pem:
            p.write_text(cert_pem)
            p.chmod(0o644)

        if key_pem:
            key_path.write_text(key_pem)
            key_path.chmod(0o600)

        if chain_pem:
            chain_path.write_text(chain_pem)
            chain_path.chmod(0o644)

        # Reload nginx
        import subprocess
        if config.nginx_reload_cmd:
            result = subprocess.run(
                config.nginx_reload_cmd,
                shell=True,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(f"nginx reload failed: {result.stderr}")

        logger.info("Deployed cert update to %s", local_path)

        # Clean up backups
        old_cert.unlink(missing_ok=True)
        old_key.unlink(missing_ok=True)

    except Exception:
        logger.exception("Failed to deploy cert to %s, restoring backups", local_path)
        if old_cert.exists():
            _restore(old_cert, p)
        if old_key.exists():
            _restore(old_key, key_path)
        raise


def _backup(src: Path, dst: Path) -> None:
    dst.write_bytes(src.read_bytes())
    dst.chmod(src.stat().st_mode)


def _restore(backup: Path, target: Path) -> None:
    target.write_bytes(backup.read_bytes())
    target.chmod(backup.stat().st_mode)
    backup.unlink(missing_ok=True)
