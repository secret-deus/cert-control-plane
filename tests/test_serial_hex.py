"""Regression tests for P0-1 / TASK-001: serial_hex format.

Validates that:
- CertManager.sign_csr() returns serial as lowercase hex string
- Serial hex fits in VARCHAR(40)
- Repeated calls produce unique serials
"""

from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

import pytest

from app.core.crypto import CertManager


def _create_test_ca():
    """Generate a throwaway CA key pair for testing."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test CA")])
    now = datetime.now(tz=timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(key, hashes.SHA256())
    )
    ca_cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    ca_key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
    return ca_cert_pem, ca_key_pem


def _create_csr(cn: str) -> bytes:
    """Generate a CSR with the given CN."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
        .sign(key, hashes.SHA256())
    )
    return csr.public_bytes(serialization.Encoding.PEM)


@pytest.fixture(scope="module")
def cert_manager():
    ca_cert_pem, ca_key_pem = _create_test_ca()
    return CertManager(ca_cert_pem, ca_key_pem)


class TestSerialHex:
    def test_sign_csr_returns_hex_string(self, cert_manager):
        """sign_csr returns (cert_pem, serial_hex) where serial_hex is hex."""
        csr = _create_csr("agent-1")
        cert_pem, serial_hex = cert_manager.sign_csr(csr, 365)

        assert isinstance(serial_hex, str)
        # Must be valid hex (no "0x" prefix, no colons)
        int(serial_hex, 16)
        assert ":" not in serial_hex
        assert serial_hex == serial_hex.lower()

    def test_serial_hex_fits_varchar40(self, cert_manager):
        """Serial hex must fit in VARCHAR(40)."""
        csr = _create_csr("agent-2")
        _, serial_hex = cert_manager.sign_csr(csr, 365)

        # x509 serial is up to 160 bits = 40 hex chars
        assert len(serial_hex) <= 40

    def test_serial_uniqueness(self, cert_manager):
        """Multiple sign operations produce unique serials."""
        serials = set()
        for i in range(20):
            csr = _create_csr(f"agent-uniq-{i}")
            _, serial_hex = cert_manager.sign_csr(csr, 365)
            serials.add(serial_hex)
        assert len(serials) == 20

    def test_issue_for_agent_serial_hex(self, cert_manager):
        """issue_for_agent returns hex serial too."""
        cert_pem, key_pem, serial_hex = cert_manager.issue_for_agent("server-agent", 365)

        assert isinstance(serial_hex, str)
        int(serial_hex, 16)
        assert len(serial_hex) <= 40
        assert serial_hex == serial_hex.lower()

    def test_cert_pem_valid(self, cert_manager):
        """Signed cert PEM can be loaded back."""
        csr = _create_csr("agent-pem-check")
        cert_pem, serial_hex = cert_manager.sign_csr(csr, 365)

        cert = x509.load_pem_x509_certificate(cert_pem)
        # Verify the cert serial matches the returned hex
        actual_hex = format(cert.serial_number, "x")
        assert actual_hex == serial_hex
