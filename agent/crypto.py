"""Agent-side cryptographic operations: key generation + CSR creation.

The private key NEVER leaves this machine.
"""

import os
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509 import CertificateSigningRequestBuilder, Name, NameAttribute
from cryptography.x509.oid import NameOID


def generate_private_key(path: Path) -> rsa.RSAPrivateKey:
    """Generate a 3072-bit RSA key and save it to *path* (mode 0600).

    Uses os.open with O_CREAT|O_WRONLY to set restrictive permissions
    atomically, avoiding a TOCTOU window where the file is world-readable.
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    path.parent.mkdir(parents=True, exist_ok=True)
    pem_bytes = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, pem_bytes)
    finally:
        os.close(fd)
    return key


def load_private_key(path: Path) -> rsa.RSAPrivateKey:
    return serialization.load_pem_private_key(path.read_bytes(), password=None)


def build_csr(key: rsa.RSAPrivateKey, cn: str) -> str:
    """Build a PEM-encoded CSR with the given Common Name."""
    csr = (
        CertificateSigningRequestBuilder()
        .subject_name(Name([NameAttribute(NameOID.COMMON_NAME, cn)]))
        .sign(key, hashes.SHA256())
    )
    return csr.public_bytes(serialization.Encoding.PEM).decode()
