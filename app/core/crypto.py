"""Crypto helpers: Fernet key encryption/decryption for external certificate storage."""

from cryptography.fernet import Fernet


# ---------------------------------------------------------------------------
# Key encryption helpers (for external certificate private key storage)
# ---------------------------------------------------------------------------


def make_fernet(key: str | bytes) -> Fernet:
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)


def encrypt_key(key_pem: bytes, fernet_key: str) -> str:
    """Encrypt a PEM private key with Fernet, returning base64-encoded ciphertext."""
    f = make_fernet(fernet_key)
    return f.encrypt(key_pem).decode()


def decrypt_key(encrypted: str, fernet_key: str) -> bytes:
    """Decrypt Fernet-encrypted private key, returning PEM bytes."""
    f = make_fernet(fernet_key)
    return f.decrypt(encrypted.encode())
