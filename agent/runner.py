"""Agent main loop: register → heartbeat → renew → deploy.

Lifecycle:
  1. If not registered: generate key + CSR → POST /register → save cert → deploy
  2. Loop forever:
     a. Check local cert expiry → proactive renewal if within threshold
     b. POST /heartbeat
     c. If pending_action == "renew": generate new key + CSR → POST /renew → save → deploy
     d. On mTLS failure (403/TLS error): attempt re-registration if bootstrap_token available
     e. Sleep heartbeat_interval
"""

import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from cryptography import x509

from agent.client import ControlPlaneClient
from agent.config import AgentConfig
from agent.crypto import build_csr, generate_private_key
from agent.deployer import deploy_to_nginx

logger = logging.getLogger(__name__)


def run(config: AgentConfig) -> None:
    """Entry point – blocks forever."""

    client = ControlPlaneClient(config)
    config.state_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Step 1: Register if needed
    # ------------------------------------------------------------------
    if not config.is_registered():
        _do_register(config, client)
    else:
        logger.info(
            "Already registered (agent_id=%s)",
            config.agent_id_path.read_text().strip(),
        )

    # ------------------------------------------------------------------
    # Step 2: Heartbeat loop
    # ------------------------------------------------------------------
    logger.info("Entering heartbeat loop (interval=%ds)", config.heartbeat_interval)
    consecutive_auth_failures = 0

    while True:
        try:
            # --- Local expiry check (proactive renewal) ---
            if _should_renew_locally(config):
                logger.info(
                    "Local cert expiring within %d days, proactively renewing",
                    config.renew_before_expiry_days,
                )
                _do_renew(config, client)
                consecutive_auth_failures = 0
                time.sleep(config.heartbeat_interval)
                continue

            # --- Heartbeat ---
            resp = client.heartbeat()
            logger.debug("Heartbeat ACK, pending_action=%s", resp.get("pending_action"))
            consecutive_auth_failures = 0  # Reset on success

            if resp.get("pending_action") == "renew":
                logger.info("Control plane requested cert renewal")
                _do_renew(config, client)

        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403):
                consecutive_auth_failures += 1
                logger.warning(
                    "mTLS authentication failed (HTTP %d), attempt %d/%d",
                    e.response.status_code,
                    consecutive_auth_failures,
                    config.max_auth_failures,
                )
                if consecutive_auth_failures >= config.max_auth_failures:
                    _handle_auth_failure(config, client)
                    consecutive_auth_failures = 0
            else:
                logger.exception("Heartbeat failed (HTTP %d), will retry", e.response.status_code)

        except (httpx.ConnectError, httpx.ReadError) as e:
            # TLS handshake failures often surface as ConnectError
            logger.warning("Connection error (possible TLS failure): %s", e)
            consecutive_auth_failures += 1
            if consecutive_auth_failures >= config.max_auth_failures:
                _handle_auth_failure(config, client)
                consecutive_auth_failures = 0

        except Exception:
            logger.exception("Heartbeat failed, will retry")

        time.sleep(config.heartbeat_interval)


# ---------------------------------------------------------------------------
# Local expiry detection
# ---------------------------------------------------------------------------


def _should_renew_locally(config: AgentConfig) -> bool:
    """Check if the local cert is expiring soon."""
    if not config.cert_path.exists():
        return False
    try:
        cert_pem = config.cert_path.read_bytes()
        cert = x509.load_pem_x509_certificate(cert_pem)
        days_left = (cert.not_valid_after_utc - datetime.now(tz=timezone.utc)).days
        logger.debug("Local cert expires in %d days", days_left)
        return days_left <= config.renew_before_expiry_days
    except Exception:
        logger.exception("Failed to parse local cert for expiry check")
        return False


# ---------------------------------------------------------------------------
# mTLS failure handling
# ---------------------------------------------------------------------------


def _handle_auth_failure(config: AgentConfig, client: ControlPlaneClient) -> None:
    """Handle persistent mTLS authentication failure.

    If a bootstrap_token is available, attempt re-registration.
    Otherwise, log an actionable error for the operator.
    """
    if config.bootstrap_token:
        logger.warning(
            "Attempting re-registration due to persistent auth failure "
            "(bootstrap_token available)"
        )
        try:
            # Clear local state to trigger fresh registration
            config.agent_id_path.unlink(missing_ok=True)
            config.cert_path.unlink(missing_ok=True)
            _do_register(config, client)
            logger.info("Re-registration succeeded")
        except Exception:
            logger.exception(
                "Re-registration failed. Manual intervention required: "
                "generate a new bootstrap token via the control plane and "
                "set CERT_AGENT_BOOTSTRAP_TOKEN"
            )
    else:
        logger.error(
            "Persistent mTLS auth failure and no bootstrap_token available. "
            "Manual intervention required: "
            "1) Generate a new bootstrap token on the control plane "
            "   (POST /api/control/agents/{id}/reset-token) "
            "2) Set CERT_AGENT_BOOTSTRAP_TOKEN in /etc/cert-agent/agent.env "
            "3) Restart cert-agent"
        )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def _do_register(config: AgentConfig, client: ControlPlaneClient) -> None:
    logger.info("Starting bootstrap registration for '%s'", config.agent_name)

    # Generate fresh private key
    key = generate_private_key(config.key_path)
    logger.info("Private key generated at %s", config.key_path)

    # Build CSR (CN = agent_name)
    csr_pem = build_csr(key, config.agent_name)

    # Call control plane
    resp = client.register(csr_pem)
    agent_id = resp["agent_id"]

    # Save cert + chain + agent_id
    _save_cert_response(config, resp)
    config.agent_id_path.write_text(str(agent_id))
    logger.info("Registered successfully, agent_id=%s", agent_id)

    # Deploy to nginx
    deploy_to_nginx(config)


# ---------------------------------------------------------------------------
# Renewal
# ---------------------------------------------------------------------------


def _do_renew(config: AgentConfig, client: ControlPlaneClient) -> None:
    logger.info("Starting cert renewal for '%s'", config.agent_name)

    # Generate a new private key (old one can be discarded after deployment succeeds)
    old_key_path = config.key_path.with_suffix(".key.old")
    old_cert_path = config.cert_path.with_suffix(".crt.old")

    # Backup current cert/key for rollback
    if config.key_path.exists():
        _backup(config.key_path, old_key_path)
    if config.cert_path.exists():
        _backup(config.cert_path, old_cert_path)

    try:
        key = generate_private_key(config.key_path)
        csr_pem = build_csr(key, config.agent_name)

        resp = client.renew(csr_pem)
        _save_cert_response(config, resp)
        logger.info("Renewal successful, new serial_hex=%s", resp.get("serial_hex"))

        deploy_to_nginx(config)

        # Clean up backups on success
        old_key_path.unlink(missing_ok=True)
        old_cert_path.unlink(missing_ok=True)

    except Exception:
        logger.exception("Renewal failed, restoring previous cert/key")
        # Restore backups
        if old_key_path.exists():
            _restore(old_key_path, config.key_path)
        if old_cert_path.exists():
            _restore(old_cert_path, config.cert_path)
        raise


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _save_cert_response(config: AgentConfig, resp: dict) -> None:
    """Save cert_pem and chain_pem from a register/renew response."""
    cert_pem = resp.get("cert_pem", "")
    chain_pem = resp.get("chain_pem", "")

    if cert_pem:
        config.cert_path.write_text(cert_pem)
        config.cert_path.chmod(0o644)

    if chain_pem:
        config.chain_path.write_text(chain_pem)
        config.chain_path.chmod(0o644)


def _backup(src: Path, dst: Path) -> None:
    dst.write_bytes(src.read_bytes())
    dst.chmod(src.stat().st_mode)


def _restore(backup: Path, target: Path) -> None:
    target.write_bytes(backup.read_bytes())
    target.chmod(backup.stat().st_mode)
    backup.unlink(missing_ok=True)
