"""Archive parser for certificate uploads (ZIP/TAR.GZ)."""

import io
import re
import tarfile
import zipfile
from dataclasses import dataclass
from datetime import datetime

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi import HTTPException


@dataclass
class CertMetadata:
    subject_cn: str
    serial_hex: str
    not_before: datetime
    not_after: datetime
    san_domains: list[str]


@dataclass
class ParsedArchive:
    cert_pem: str
    key_pem: str
    chain_pem: str | None
    cert_filename: str
    key_filename: str
    chain_filename: str | None
    metadata: CertMetadata


@dataclass
class FileDetection:
    cert_file: str | None
    key_file: str | None
    chain_file: str | None
    all_files: list[str]


MAX_ARCHIVE_SIZE = 10 * 1024 * 1024
MAX_EXTRACTED_SIZE = 50 * 1024 * 1024


class ArchiveParser:
    @staticmethod
    def parse(archive_bytes: bytes, filename: str) -> ParsedArchive:
        if len(archive_bytes) > MAX_ARCHIVE_SIZE:
            raise HTTPException(
                status_code=400, detail="Archive file exceeds 10MB limit."
            )

        lowered = filename.lower()
        if lowered.endswith(".zip"):
            files = ArchiveParser._extract_zip(archive_bytes)
        elif lowered.endswith(".tar.gz") or lowered.endswith(".tgz"):
            files = ArchiveParser._extract_tar(archive_bytes, lowered)
        else:
            raise HTTPException(
                status_code=400,
                detail="Unsupported archive format. Only .zip and .tar.gz are allowed.",
            )

        detection = ArchiveParser._detect_files(files)

        if not detection.key_file:
            raise HTTPException(
                status_code=400, detail="No .key file found in archive."
            )
        if not detection.cert_file:
            raise HTTPException(
                status_code=400, detail="No .pem file found in archive."
            )

        cert_content = files[detection.cert_file]
        key_content = files[detection.key_file]
        chain_content = (
            files.get(detection.chain_file) if detection.chain_file else None
        )

        cert_pem, chain_from_cert = CertParser.split_fullchain(cert_content)
        final_chain = chain_content or chain_from_cert

        metadata = CertParser.parse_certificate(cert_pem)

        if not KeyValidator.validate_key_match(cert_pem, key_content):
            raise HTTPException(
                status_code=400, detail="Certificate and private key do not match."
            )

        return ParsedArchive(
            cert_pem=cert_pem,
            key_pem=key_content,
            chain_pem=final_chain,
            cert_filename=detection.cert_file,
            key_filename=detection.key_file,
            chain_filename=detection.chain_file,
            metadata=metadata,
        )

    @staticmethod
    def _extract_zip(archive_bytes: bytes) -> dict[str, str]:
        files = {}
        total_extracted = 0
        try:
            with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    if ".." in info.filename or info.filename.startswith("/"):
                        raise HTTPException(
                            status_code=400,
                            detail=f"Unsafe path in archive: {info.filename}",
                        )
                    name = info.filename
                    if name.lower().endswith((".pem", ".key")):
                        content = zf.read(info.filename).decode("utf-8")
                        total_extracted += len(content.encode("utf-8"))
                        if total_extracted > MAX_EXTRACTED_SIZE:
                            raise HTTPException(
                                status_code=400,
                                detail="Extracted data exceeds 50MB limit (compression bomb detected)",
                            )
                        files[name] = content
        except zipfile.BadZipFile as e:
            raise HTTPException(
                status_code=400, detail=f"Failed to extract archive: {e}"
            )
        return files

    @staticmethod
    def _extract_tar(archive_bytes: bytes, filename: str) -> dict[str, str]:
        files = {}
        total_extracted = 0
        try:
            mode = "r:gz"
            with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode=mode) as tf:
                for member in tf.getmembers():
                    if not member.isfile():
                        continue
                    if ".." in member.name or member.name.startswith("/"):
                        raise HTTPException(
                            status_code=400,
                            detail=f"Unsafe path in archive: {member.name}",
                        )
                    name = member.name
                    if name.lower().endswith((".pem", ".key")):
                        f = tf.extractfile(member)
                        if f:
                            content = f.read().decode("utf-8")
                            total_extracted += len(content.encode("utf-8"))
                            if total_extracted > MAX_EXTRACTED_SIZE:
                                raise HTTPException(
                                    status_code=400,
                                    detail="Extracted data exceeds 50MB limit (compression bomb detected)",
                                )
                            files[name] = content
        except tarfile.TarError as e:
            raise HTTPException(
                status_code=400, detail=f"Failed to extract archive: {e}"
            )
        return files

    @staticmethod
    def _detect_files(files: dict[str, str]) -> FileDetection:
        key_files = []
        pem_files = []

        for filename in files.keys():
            base = filename.lower()
            if base.endswith(".key"):
                key_files.append(filename)
            elif base.endswith(".pem"):
                pem_files.append(filename)

        if len(key_files) > 1:
            raise HTTPException(
                status_code=400,
                detail="Multiple .key files found. Please upload a single pair.",
            )

        if len(pem_files) > 1:
            chain_files = [f for f in pem_files if "chain" in f.lower()]
            cert_files = [f for f in pem_files if "chain" not in f.lower()]

            if len(cert_files) > 1:
                raise HTTPException(
                    status_code=400,
                    detail="Multiple certificate pairs found. Please upload a single pair.",
                )

            cert_file = cert_files[0] if cert_files else pem_files[0]
            chain_file = chain_files[0] if chain_files else None
        elif len(pem_files) == 1:
            cert_file = pem_files[0]
            chain_file = None
        else:
            cert_file = None
            chain_file = None

        return FileDetection(
            cert_file=cert_file,
            key_file=key_files[0] if key_files else None,
            chain_file=chain_file,
            all_files=list(files.keys()),
        )


class CertParser:
    @staticmethod
    def parse_certificate(cert_pem: str) -> CertMetadata:
        try:
            cert = x509.load_pem_x509_certificate(cert_pem.encode())
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid certificate PEM: {e}")

        cn_attrs = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        if not cn_attrs:
            raise HTTPException(
                status_code=400, detail="Certificate missing Common Name"
            )
        subject_cn = cn_attrs[0].value

        serial_hex = format(cert.serial_number, "x").lower()

        san_domains = []
        try:
            san_ext = cert.extensions.get_extension_for_oid(
                x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
            )
            san = san_ext.value
            for name in san:
                if isinstance(name, x509.DNSName):
                    san_domains.append(name.value)
        except x509.ExtensionNotFound:
            pass

        return CertMetadata(
            subject_cn=subject_cn,
            serial_hex=serial_hex,
            not_before=cert.not_valid_before_utc,
            not_after=cert.not_valid_after_utc,
            san_domains=san_domains,
        )

    @staticmethod
    def split_fullchain(pem_content: str) -> tuple[str, str | None]:
        pattern = r"-----BEGIN CERTIFICATE-----[\s\S]*?-----END CERTIFICATE-----"
        matches = re.findall(pattern, pem_content)

        if not matches:
            raise HTTPException(
                status_code=400, detail="No valid certificate found in PEM."
            )

        cert_pem = matches[0].strip()

        if len(matches) > 1:
            chain_pem = "\n".join(matches[1:]).strip()
            return cert_pem, chain_pem

        return cert_pem, None


class KeyValidator:
    @staticmethod
    def parse_key(key_pem: str):
        try:
            key = serialization.load_pem_private_key(
                key_pem.encode(),
                password=None,
            )
            return key
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid private key PEM: {e}")

    @staticmethod
    def validate_key_match(cert_pem: str, key_pem: str) -> bool:
        try:
            cert = x509.load_pem_x509_certificate(cert_pem.encode())
            key = KeyValidator.parse_key(key_pem)

            if not isinstance(key, rsa.RSAPrivateKey):
                return False

            cert_public_key = cert.public_key()
            if not isinstance(cert_public_key, rsa.RSAPublicKey):
                return False

            cert_modulus = cert_public_key.public_numbers().n
            key_modulus = key.public_key().public_numbers().n

            return cert_modulus == key_modulus
        except Exception:
            return False
