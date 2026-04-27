"""Tests for archive parser service."""

import io
import tarfile
import zipfile
from datetime import datetime, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi import HTTPException

from app.services.archive_parser import (
    ArchiveParser,
    CertParser,
    KeyValidator,
    MAX_ARCHIVE_SIZE,
)


def generate_test_cert_key_pair(cn: str = "test.example.com"):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    key_pem_pkcs1 = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    key_pem_pkcs8 = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, cn),
        ]
    )

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime(2024, 1, 1, tzinfo=timezone.utc))
        .not_valid_after(datetime(2027, 1, 1, tzinfo=timezone.utc))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName(cn),
                    x509.DNSName(f"www.{cn}"),
                ]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()

    return cert_pem, key_pem_pkcs1, key_pem_pkcs8


def create_zip_archive(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename, content in files.items():
            zf.writestr(filename, content)
    return buf.getvalue()


def create_tar_gz_archive(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for filename, content in files.items():
            data = content.encode()
            info = tarfile.TarInfo(name=filename)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class TestArchiveParserExtract:
    def test_extract_zip_valid(self):
        cert_pem, key_pem, _ = generate_test_cert_key_pair()
        archive_bytes = create_zip_archive(
            {
                "test.example.com.key": key_pem,
                "test.example.com.pem": cert_pem,
            }
        )

        files = ArchiveParser._extract_zip(archive_bytes)

        assert "test.example.com.key" in files
        assert "test.example.com.pem" in files
        assert files["test.example.com.key"] == key_pem
        assert files["test.example.com.pem"] == cert_pem

    def test_extract_zip_with_subdirectory(self):
        cert_pem, key_pem, _ = generate_test_cert_key_pair()
        archive_bytes = create_zip_archive(
            {
                "certs/test.example.com.key": key_pem,
                "certs/test.example.com.pem": cert_pem,
            }
        )

        files = ArchiveParser._extract_zip(archive_bytes)

        assert "certs/test.example.com.key" in files
        assert "certs/test.example.com.pem" in files

    def test_extract_zip_path_traversal_raises(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../../../etc/passwd", "malicious")

        with pytest.raises(HTTPException) as exc:
            ArchiveParser._extract_zip(buf.getvalue())

        assert exc.value.status_code == 400
        assert "Unsafe path" in exc.value.detail

    def test_extract_zip_absolute_path_raises(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("/etc/passwd", "malicious")

        with pytest.raises(HTTPException) as exc:
            ArchiveParser._extract_zip(buf.getvalue())

        assert exc.value.status_code == 400

    def test_extract_tar_gz_valid(self):
        cert_pem, key_pem, _ = generate_test_cert_key_pair()
        archive_bytes = create_tar_gz_archive(
            {
                "test.example.com.key": key_pem,
                "test.example.com.pem": cert_pem,
            }
        )

        files = ArchiveParser._extract_tar(archive_bytes, "test.tar.gz")

        assert "test.example.com.key" in files
        assert "test.example.com.pem" in files

    def test_extract_tar_gz_path_traversal_raises(self):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            data = b"malicious"
            info = tarfile.TarInfo(name="../../../etc/passwd")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))

        with pytest.raises(HTTPException) as exc:
            ArchiveParser._extract_tar(buf.getvalue(), "test.tar.gz")

        assert exc.value.status_code == 400


class TestArchiveParserDetect:
    def test_detect_standard_files(self):
        files = {
            "api.example.com.key": "-----BEGIN PRIVATE KEY-----\nkey\n-----END PRIVATE KEY-----",
            "api.example.com.pem": "-----BEGIN CERTIFICATE-----\ncert\n-----END CERTIFICATE-----",
        }

        detection = ArchiveParser._detect_files(files)

        assert detection.key_file == "api.example.com.key"
        assert detection.cert_file == "api.example.com.pem"
        assert detection.chain_file is None

    def test_detect_fullchain(self):
        files = {
            "test.key": "-----BEGIN PRIVATE KEY-----\nkey\n-----END PRIVATE KEY-----",
            "fullchain.pem": "-----BEGIN CERTIFICATE-----\nleaf\n-----END CERTIFICATE-----\n-----BEGIN CERTIFICATE-----\nchain\n-----END CERTIFICATE-----",
        }

        detection = ArchiveParser._detect_files(files)

        assert detection.cert_file == "fullchain.pem"

    def test_detect_chain_file(self):
        files = {
            "test.key": "-----BEGIN PRIVATE KEY-----\nkey\n-----END PRIVATE KEY-----",
            "test.pem": "-----BEGIN CERTIFICATE-----\ncert\n-----END CERTIFICATE-----",
            "chain.pem": "-----BEGIN CERTIFICATE-----\nchain\n-----END CERTIFICATE-----",
        }

        detection = ArchiveParser._detect_files(files)

        assert detection.cert_file == "test.pem"
        assert detection.chain_file == "chain.pem"

    def test_detect_multiple_key_files_raises(self):
        files = {
            "test1.key": "-----BEGIN PRIVATE KEY-----\nkey1\n-----END PRIVATE KEY-----",
            "test2.key": "-----BEGIN PRIVATE KEY-----\nkey2\n-----END PRIVATE KEY-----",
            "test.pem": "-----BEGIN CERTIFICATE-----\ncert\n-----END CERTIFICATE-----",
        }

        with pytest.raises(HTTPException) as exc:
            ArchiveParser._detect_files(files)

        assert exc.value.status_code == 400
        assert "Multiple private key files" in exc.value.detail

    def test_detect_multiple_cert_pairs_raises(self):
        files = {
            "test.key": "-----BEGIN PRIVATE KEY-----\nkey\n-----END PRIVATE KEY-----",
            "test1.pem": "-----BEGIN CERTIFICATE-----\ncert1\n-----END CERTIFICATE-----",
            "test2.pem": "-----BEGIN CERTIFICATE-----\ncert2\n-----END CERTIFICATE-----",
        }

        with pytest.raises(HTTPException) as exc:
            ArchiveParser._detect_files(files)

        assert exc.value.status_code == 400
        assert "Multiple certificate pairs" in exc.value.detail

    def test_detect_crt_and_pem_key_files(self):
        files = {
            "admin.example.com.crt": "-----BEGIN CERTIFICATE-----\ncert\n-----END CERTIFICATE-----",
            "privkey.pem": "-----BEGIN PRIVATE KEY-----\nkey\n-----END PRIVATE KEY-----",
        }

        detection = ArchiveParser._detect_files(files)

        assert detection.cert_file == "admin.example.com.crt"
        assert detection.key_file == "privkey.pem"


class TestArchiveParserParse:
    def test_parse_zip_success(self):
        cert_pem, key_pem, _ = generate_test_cert_key_pair("api.example.com")
        archive_bytes = create_zip_archive(
            {
                "api.example.com.key": key_pem,
                "api.example.com.pem": cert_pem,
            }
        )

        result = ArchiveParser.parse(archive_bytes, "test.zip")

        assert result.cert_pem.strip() == cert_pem.strip()
        assert result.key_pem.strip() == key_pem.strip()
        assert result.cert_filename == "api.example.com.pem"
        assert result.key_filename == "api.example.com.key"
        assert result.metadata.subject_cn == "api.example.com"
        assert len(result.metadata.san_domains) == 2

    def test_parse_tar_gz_success(self):
        cert_pem, key_pem, _ = generate_test_cert_key_pair("api.example.com")
        archive_bytes = create_tar_gz_archive(
            {
                "api.example.com.key": key_pem,
                "api.example.com.pem": cert_pem,
            }
        )

        result = ArchiveParser.parse(archive_bytes, "test.tar.gz")

        assert result.metadata.subject_cn == "api.example.com"

    def test_parse_tgz_extension(self):
        cert_pem, key_pem, _ = generate_test_cert_key_pair()
        archive_bytes = create_tar_gz_archive(
            {
                "test.key": key_pem,
                "test.pem": cert_pem,
            }
        )

        result = ArchiveParser.parse(archive_bytes, "test.tgz")

        assert result.cert_pem.strip() == cert_pem.strip()

    def test_parse_zip_success_with_crt_and_pem_key(self):
        cert_pem, key_pem, _ = generate_test_cert_key_pair("admin.example.com")
        archive_bytes = create_zip_archive(
            {
                "admin.example.com.crt": cert_pem,
                "privkey.pem": key_pem,
            }
        )

        result = ArchiveParser.parse(archive_bytes, "test.zip")

        assert result.cert_filename == "admin.example.com.crt"
        assert result.key_filename == "privkey.pem"
        assert result.metadata.subject_cn == "admin.example.com"

    def test_parse_zip_success_with_fullchain_and_privkey_pem(self):
        cert_pem, key_pem, _ = generate_test_cert_key_pair("admin.example.com")
        chain_pem, _, _ = generate_test_cert_key_pair("chain.example.com")
        archive_bytes = create_zip_archive(
            {
                "fullchain.pem": f"{cert_pem}\n{chain_pem}",
                "privkey.pem": key_pem,
            }
        )

        result = ArchiveParser.parse(archive_bytes, "test.zip")

        assert result.cert_filename == "fullchain.pem"
        assert result.key_filename == "privkey.pem"
        assert result.chain_pem is not None

    def test_parse_exceeds_size_limit(self):
        large_bytes = b"x" * (MAX_ARCHIVE_SIZE + 1)

        with pytest.raises(HTTPException) as exc:
            ArchiveParser.parse(large_bytes, "test.zip")

        assert exc.value.status_code == 400
        assert "exceeds 10MB" in exc.value.detail

    def test_parse_unsupported_format(self):
        with pytest.raises(HTTPException) as exc:
            ArchiveParser.parse(b"content", "test.rar")

        assert exc.value.status_code == 400
        assert "Unsupported archive format" in exc.value.detail

    def test_parse_missing_key_file(self):
        cert_pem, _, _ = generate_test_cert_key_pair()
        archive_bytes = create_zip_archive(
            {
                "test.pem": cert_pem,
            }
        )

        with pytest.raises(HTTPException) as exc:
            ArchiveParser.parse(archive_bytes, "test.zip")

        assert exc.value.status_code == 400
        assert "No private key file" in exc.value.detail

    def test_parse_missing_certificate_file(self):
        _, key_pem, _ = generate_test_cert_key_pair()
        archive_bytes = create_zip_archive(
            {
                "test.key": key_pem,
            }
        )

        with pytest.raises(HTTPException) as exc:
            ArchiveParser.parse(archive_bytes, "test.zip")

        assert exc.value.status_code == 400
        assert "No certificate file" in exc.value.detail

    def test_parse_key_mismatch(self):
        cert_pem, _, _ = generate_test_cert_key_pair("test1.example.com")
        _, key_pem, _ = generate_test_cert_key_pair("test2.example.com")

        archive_bytes = create_zip_archive(
            {
                "test.key": key_pem,
                "test.pem": cert_pem,
            }
        )

        with pytest.raises(HTTPException) as exc:
            ArchiveParser.parse(archive_bytes, "test.zip")

        assert exc.value.status_code == 400
        assert "do not match" in exc.value.detail


class TestCertParser:
    def test_parse_certificate_cn(self):
        cert_pem, _, _ = generate_test_cert_key_pair("api.example.com")

        metadata = CertParser.parse_certificate(cert_pem)

        assert metadata.subject_cn == "api.example.com"

    def test_parse_certificate_serial_hex(self):
        cert_pem, _, _ = generate_test_cert_key_pair()

        metadata = CertParser.parse_certificate(cert_pem)

        assert metadata.serial_hex
        assert len(metadata.serial_hex) > 0

    def test_parse_certificate_validity(self):
        cert_pem, _, _ = generate_test_cert_key_pair()

        metadata = CertParser.parse_certificate(cert_pem)

        assert metadata.not_before
        assert metadata.not_after
        assert metadata.not_after > metadata.not_before

    def test_parse_certificate_san(self):
        cert_pem, _, _ = generate_test_cert_key_pair("api.example.com")

        metadata = CertParser.parse_certificate(cert_pem)

        assert "api.example.com" in metadata.san_domains
        assert "www.api.example.com" in metadata.san_domains

    def test_parse_certificate_invalid_pem(self):
        with pytest.raises(HTTPException) as exc:
            CertParser.parse_certificate("not a valid pem")

        assert exc.value.status_code == 400
        assert "Invalid certificate PEM" in exc.value.detail

    def test_split_fullchain_single_cert(self):
        cert_pem, _, _ = generate_test_cert_key_pair()

        cert, chain = CertParser.split_fullchain(cert_pem)

        assert cert.strip() == cert_pem.strip()
        assert chain is None

    def test_split_fullchain_with_chain(self):
        cert_pem, _, _ = generate_test_cert_key_pair()
        chain_pem = cert_pem.replace("test.example.com", "chain.example.com")
        fullchain = f"{cert_pem}\n{chain_pem}"

        cert, chain = CertParser.split_fullchain(fullchain)

        assert cert.strip() == cert_pem.strip()
        assert chain.strip() == chain_pem.strip()

    def test_split_fullchain_no_cert_raises(self):
        with pytest.raises(HTTPException) as exc:
            CertParser.split_fullchain("no certificate here")

        assert exc.value.status_code == 400
        assert "No valid certificate" in exc.value.detail


class TestKeyValidator:
    def test_parse_key_pkcs1(self):
        _, key_pem_pkcs1, _ = generate_test_cert_key_pair()

        key = KeyValidator.parse_key(key_pem_pkcs1)

        assert key is not None

    def test_parse_key_pkcs8(self):
        _, _, key_pem_pkcs8 = generate_test_cert_key_pair()

        key = KeyValidator.parse_key(key_pem_pkcs8)

        assert key is not None

    def test_validate_key_match_true(self):
        cert_pem, key_pem, _ = generate_test_cert_key_pair()

        result = KeyValidator.validate_key_match(cert_pem, key_pem)

        assert result is True

    def test_validate_key_match_false(self):
        cert_pem, _, _ = generate_test_cert_key_pair("test1.example.com")
        _, key_pem, _ = generate_test_cert_key_pair("test2.example.com")

        result = KeyValidator.validate_key_match(cert_pem, key_pem)

        assert result is False

    def test_validate_key_match_invalid_key(self):
        cert_pem, _, _ = generate_test_cert_key_pair()

        result = KeyValidator.validate_key_match(cert_pem, "invalid key")

        assert result is False

    def test_parse_key_invalid(self):
        with pytest.raises(HTTPException) as exc:
            KeyValidator.parse_key("not a valid key")

        assert exc.value.status_code == 400
        assert "Invalid private key PEM" in exc.value.detail
