"""Agent-side cryptographic operations: key generation and fingerprint computation.

The private key NEVER leaves this machine.
"""

import hashlib
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def generate_key_pair(key_path: Path) -> rsa.RSAPrivateKey:
    """Generate a 3072-bit RSA key pair, save private key to *key_path* (mode 0600).

    Returns the private key object.
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    pem_bytes = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    # Write atomically with restricted permissions
    fd = os.open(str(key_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, pem_bytes)
    finally:
        os.close(fd)
    return key


def load_private_key(key_path: Path) -> rsa.RSAPrivateKey:
    """Load RSA private key from PEM file."""
    return serialization.load_pem_private_key(key_path.read_bytes(), password=None)


def compute_fingerprint(key: rsa.RSAPrivateKey) -> str:
    """Compute SHA256 fingerprint of the public key (DER encoded).

    Returns lowercase hex string (64 chars).
    This is sent to the control plane as TOFU identity.
    """
    pub_key = key.public_key()
    pub_der = pub_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return hashlib.sha256(pub_der).hexdigest()
