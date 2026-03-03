"""CA operations: load CA, sign CSR, generate key pair, encrypt/decrypt key."""

from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


class CertManager:
    """Wraps CA cert+key to sign CSRs and generate key pairs."""

    def __init__(self, ca_cert_pem: bytes, ca_key_pem: bytes) -> None:
        self.ca_cert = x509.load_pem_x509_certificate(ca_cert_pem)
        self.ca_key = serialization.load_pem_private_key(ca_key_pem, password=None)

    # ------------------------------------------------------------------
    # Key generation
    # ------------------------------------------------------------------

    @staticmethod
    def generate_private_key() -> rsa.RSAPrivateKey:
        return rsa.generate_private_key(public_exponent=65537, key_size=2048)

    @staticmethod
    def private_key_to_pem(key: rsa.RSAPrivateKey) -> bytes:
        return key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )

    # ------------------------------------------------------------------
    # CSR signing
    # ------------------------------------------------------------------

    def sign_csr(
        self,
        csr_pem: str | bytes,
        validity_days: int = 365,
    ) -> tuple[bytes, str]:
        """Sign a PEM CSR and return (cert_pem, serial_hex).

        serial_hex is the certificate serial number as lowercase hex string,
        safe for storage in VARCHAR (x509 serials can be up to 160 bits).
        """
        if isinstance(csr_pem, str):
            csr_pem = csr_pem.encode()

        csr = x509.load_pem_x509_csr(csr_pem)
        cn = csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value

        serial = x509.random_serial_number()
        now = datetime.now(tz=timezone.utc)

        builder = (
            x509.CertificateBuilder()
            .subject_name(csr.subject)
            .issuer_name(self.ca_cert.subject)
            .public_key(csr.public_key())
            .serial_number(serial)
            .not_valid_before(now)
            .not_valid_after(now + timedelta(days=validity_days))
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None), critical=True
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    key_encipherment=True,
                    content_commitment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(
                x509.ExtendedKeyUsage([
                    ExtendedKeyUsageOID.CLIENT_AUTH,
                    ExtendedKeyUsageOID.SERVER_AUTH,
                ]),
                critical=False,
            )
            .add_extension(
                x509.SubjectAlternativeName([x509.DNSName(cn)]),
                critical=False,
            )
        )

        cert = builder.sign(self.ca_key, hashes.SHA256())
        cert_pem = cert.public_bytes(serialization.Encoding.PEM)
        serial_hex = format(serial, "x")
        return cert_pem, serial_hex

    def issue_for_agent(
        self,
        cn: str,
        validity_days: int = 365,
    ) -> tuple[bytes, bytes, str]:
        """Generate key + cert for agent (server-side keygen).
        Returns (cert_pem, key_pem, serial_hex).
        """
        key = self.generate_private_key()
        key_pem = self.private_key_to_pem(key)

        # Build a minimal CSR internally
        csr = (
            x509.CertificateSigningRequestBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
            .sign(key, hashes.SHA256())
        )
        csr_pem = csr.public_bytes(serialization.Encoding.PEM)

        cert_pem, serial_hex = self.sign_csr(csr_pem, validity_days)
        return cert_pem, key_pem, serial_hex

    def ca_cert_pem(self) -> bytes:
        return self.ca_cert.public_bytes(serialization.Encoding.PEM)

    # ------------------------------------------------------------------
    # Fingerprint
    # ------------------------------------------------------------------

    @staticmethod
    def fingerprint(cert_pem: str | bytes) -> str:
        if isinstance(cert_pem, str):
            cert_pem = cert_pem.encode()
        cert = x509.load_pem_x509_certificate(cert_pem)
        fp = cert.fingerprint(hashes.SHA256())
        return fp.hex()


# ---------------------------------------------------------------------------
# Key encryption helpers
# ---------------------------------------------------------------------------


def make_fernet(key: str | bytes) -> Fernet:
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)


def encrypt_key(key_pem: bytes, fernet_key: str) -> str:
    f = make_fernet(fernet_key)
    return f.encrypt(key_pem).decode()


def decrypt_key(encrypted: str, fernet_key: str) -> bytes:
    f = make_fernet(fernet_key)
    return f.decrypt(encrypted.encode())


# ---------------------------------------------------------------------------
# CA loader (singleton)
# ---------------------------------------------------------------------------

_cert_manager: CertManager | None = None


def load_ca(ca_cert_path: str, ca_key_path: str) -> CertManager:
    global _cert_manager
    if _cert_manager is None:
        with open(ca_cert_path, "rb") as f:
            ca_cert_pem = f.read()
        with open(ca_key_path, "rb") as f:
            ca_key_pem = f.read()
        _cert_manager = CertManager(ca_cert_pem, ca_key_pem)
    return _cert_manager


def get_cert_manager() -> CertManager:
    if _cert_manager is None:
        raise RuntimeError("CA not loaded – call load_ca() during startup")
    return _cert_manager
