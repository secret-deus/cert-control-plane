"""Tests for app.core.crypto – Fernet key encryption/decryption helpers.

CertManager was removed in the distribution-mode refactor.
These tests cover the remaining crypto utilities.
"""

import pytest
from cryptography.fernet import Fernet

from app.core.crypto import decrypt_key, encrypt_key, make_fernet


# ---------------------------------------------------------------------------
# make_fernet
# ---------------------------------------------------------------------------


def _valid_fernet_key() -> str:
    return Fernet.generate_key().decode()


class TestMakeFernet:
    def test_returns_fernet_instance(self):
        key = _valid_fernet_key()
        f = make_fernet(key)
        assert isinstance(f, Fernet)

    def test_invalid_key_raises(self):
        with pytest.raises(Exception):
            make_fernet("not-a-valid-key")


# ---------------------------------------------------------------------------
# encrypt_key / decrypt_key round-trip
# ---------------------------------------------------------------------------


class TestEncryptDecryptKey:
    def test_roundtrip(self):
        fernet_key = _valid_fernet_key()
        plaintext = b"-----BEGIN PRIVATE KEY-----\nFAKEKEY\n-----END PRIVATE KEY-----"

        encrypted = encrypt_key(plaintext, fernet_key)

        assert isinstance(encrypted, str)
        assert encrypted != plaintext.decode()

        recovered = decrypt_key(encrypted, fernet_key)
        assert recovered == plaintext

    def test_encrypted_is_different_each_time(self):
        """Fernet uses random IV; two encryptions of the same data differ."""
        fernet_key = _valid_fernet_key()
        data = b"some-key-data"

        enc1 = encrypt_key(data, fernet_key)
        enc2 = encrypt_key(data, fernet_key)

        assert enc1 != enc2

    def test_wrong_key_raises_on_decrypt(self):
        fernet_key = _valid_fernet_key()
        wrong_key = _valid_fernet_key()
        data = b"secret-key"

        encrypted = encrypt_key(data, fernet_key)

        with pytest.raises(Exception):
            decrypt_key(encrypted, wrong_key)
