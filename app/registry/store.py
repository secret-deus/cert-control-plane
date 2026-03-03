"""Certificate Registry – create, retrieve, and revoke certs in the DB."""

import uuid
from datetime import datetime, timezone

from cryptography import x509 as _x509
from cryptography.x509.oid import NameOID
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.crypto import CertManager, decrypt_key, encrypt_key, get_cert_manager
from app.models import Agent, AgentStatus, Certificate


class CertRegistry:
    """CRUD operations for the certificate store."""

    # ------------------------------------------------------------------
    # Write: issue a new cert
    # ------------------------------------------------------------------

    async def issue_from_csr(
        self,
        db: AsyncSession,
        *,
        agent: Agent,
        csr_pem: str,
    ) -> Certificate:
        """Sign a CSR submitted by an agent (agent-generated key).

        Validates that the CSR's CN matches the agent name to prevent
        impersonation.
        """
        settings = get_settings()
        mgr: CertManager = get_cert_manager()

        # Validate CSR CN matches agent name
        if isinstance(csr_pem, str):
            csr_raw = csr_pem.encode()
        else:
            csr_raw = csr_pem
        csr = _x509.load_pem_x509_csr(csr_raw)
        csr_cn_attrs = csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        if not csr_cn_attrs:
            raise ValueError("CSR missing Common Name (CN)")
        csr_cn = csr_cn_attrs[0].value
        if csr_cn != agent.name:
            raise ValueError(
                f"CSR CN '{csr_cn}' does not match agent name '{agent.name}'"
            )

        cert_pem_bytes, serial_hex = mgr.sign_csr(csr_pem, settings.cert_validity_days)
        cert_pem = cert_pem_bytes.decode()
        c = _x509.load_pem_x509_certificate(cert_pem_bytes)

        cert = Certificate(
            agent_id=agent.id,
            serial_hex=serial_hex,
            subject_cn=c.subject.get_attributes_for_oid(
                _x509.oid.NameOID.COMMON_NAME
            )[0].value,
            not_before=c.not_valid_before_utc,
            not_after=c.not_valid_after_utc,
            cert_pem=cert_pem,
            key_pem_encrypted=None,  # Agent owns the key
            chain_pem=mgr.ca_cert_pem().decode(),
            is_current=True,
        )
        db.add(cert)

        # Mark old certs as superseded
        await db.execute(
            update(Certificate)
            .where(
                Certificate.agent_id == agent.id,
                Certificate.id != cert.id,
                Certificate.is_current.is_(True),
            )
            .values(is_current=False)
        )

        # Update agent fingerprint and status
        agent.fingerprint = CertManager.fingerprint(cert_pem_bytes)
        agent.status = AgentStatus.ACTIVE
        db.add(agent)

        await db.flush()
        return cert

    async def issue_server_side(
        self,
        db: AsyncSession,
        *,
        agent: Agent,
    ) -> Certificate:
        """Generate key + cert server-side (used for initial bootstrap if no CSR)."""
        settings = get_settings()
        mgr: CertManager = get_cert_manager()

        cert_pem_bytes, key_pem_bytes, serial_hex = mgr.issue_for_agent(
            agent.name, settings.cert_validity_days
        )
        cert_pem = cert_pem_bytes.decode()

        # Encrypt key with Fernet before storage
        key_pem_enc = encrypt_key(key_pem_bytes, settings.ca_key_encryption_key)

        c = _x509.load_pem_x509_certificate(cert_pem_bytes)

        cert = Certificate(
            agent_id=agent.id,
            serial_hex=serial_hex,
            subject_cn=c.subject.get_attributes_for_oid(
                _x509.oid.NameOID.COMMON_NAME
            )[0].value,
            not_before=c.not_valid_before_utc,
            not_after=c.not_valid_after_utc,
            cert_pem=cert_pem,
            key_pem_encrypted=key_pem_enc,
            chain_pem=mgr.ca_cert_pem().decode(),
            is_current=True,
        )
        db.add(cert)

        await db.execute(
            update(Certificate)
            .where(
                Certificate.agent_id == agent.id,
                Certificate.id != cert.id,
                Certificate.is_current.is_(True),
            )
            .values(is_current=False)
        )

        agent.fingerprint = CertManager.fingerprint(cert_pem_bytes)
        agent.status = AgentStatus.ACTIVE
        db.add(agent)

        await db.flush()
        return cert

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_current_cert(
        self, db: AsyncSession, agent_id: uuid.UUID
    ) -> Certificate | None:
        result = await db.execute(
            select(Certificate).where(
                Certificate.agent_id == agent_id,
                Certificate.is_current.is_(True),
                Certificate.revoked_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_cert_by_id(
        self, db: AsyncSession, cert_id: uuid.UUID
    ) -> Certificate | None:
        result = await db.execute(
            select(Certificate).where(Certificate.id == cert_id)
        )
        return result.scalar_one_or_none()

    async def list_certs_for_agent(
        self, db: AsyncSession, agent_id: uuid.UUID
    ) -> list[Certificate]:
        result = await db.execute(
            select(Certificate)
            .where(Certificate.agent_id == agent_id)
            .order_by(Certificate.created_at.desc())
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Bundle: cert + chain (+ key if server-generated)
    # NOTE: key returned ONLY via agent-authenticated endpoint
    # ------------------------------------------------------------------

    def build_bundle(
        self, cert: Certificate, *, include_key: bool = False
    ) -> dict[str, str | None]:
        """Build the downloadable bundle dict."""
        settings = get_settings()
        bundle: dict[str, str | None] = {
            "cert_pem": cert.cert_pem,
            "chain_pem": cert.chain_pem,
            "key_pem": None,
        }
        if include_key and cert.key_pem_encrypted:
            if not settings.ca_key_encryption_key:
                raise RuntimeError("CA_KEY_ENCRYPTION_KEY not configured")
            bundle["key_pem"] = decrypt_key(
                cert.key_pem_encrypted, settings.ca_key_encryption_key
            ).decode()
        return bundle

    # ------------------------------------------------------------------
    # Revoke
    # ------------------------------------------------------------------

    async def revoke(
        self, db: AsyncSession, cert: Certificate
    ) -> Certificate:
        cert.revoked_at = datetime.now(tz=timezone.utc)
        cert.is_current = False
        db.add(cert)
        await db.flush()
        return cert


registry = CertRegistry()
