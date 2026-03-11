#!/usr/bin/env python3
"""Generate a self-signed CA certificate and server TLS certificate.

Usage:
    python scripts/init_ca.py [--out-dir ./certs]

Outputs:
    certs/ca.key          CA private key (keep secret!)
    certs/ca.crt          CA certificate (distribute to agents as trust anchor)
    certs/server.key      Server TLS private key
    certs/server.crt      Server TLS certificate (signed by CA)
"""

import argparse
import datetime
import os
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def gen_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=4096)


def save_key(key: rsa.RSAPrivateKey, path: Path) -> None:
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    os.chmod(path, 0o600)
    print(f"  Wrote {path}")


def save_cert(cert: x509.Certificate, path: Path) -> None:
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    print(f"  Wrote {path}")


def build_ca(cn: str = "Cert Control Plane CA") -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    key = gen_key()
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, cn),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Cert Control Plane"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=1825))  # 5 years
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_cert_sign=True,
                crl_sign=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    return key, cert


def build_server_cert(
    ca_key: rsa.RSAPrivateKey,
    ca_cert: x509.Certificate,
    cn: str = "cert-control-plane",
    sans: list[str] | None = None,
) -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    key = gen_key()
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])

    dns_names = [x509.DNSName(cn), x509.DNSName("localhost")]
    if sans:
        dns_names += [x509.DNSName(s) for s in sans]
    dns_names.append(x509.IPAddress(__import__("ipaddress").IPv4Address("127.0.0.1")))

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=398))  # ~13 months (browser limit)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName(dns_names), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    return key, cert


def main():
    parser = argparse.ArgumentParser(description="Initialize CA and server TLS certs")
    parser.add_argument("--out-dir", default="./certs", help="Output directory")
    parser.add_argument("--server-cn", default="cert-control-plane")
    parser.add_argument("--sans", nargs="*", default=[], help="Additional SANs")
    args = parser.parse_args()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    os.chmod(out, 0o700)

    print("Generating CA...")
    ca_key, ca_cert = build_ca()
    save_key(ca_key, out / "ca.key")
    save_cert(ca_cert, out / "ca.crt")

    print("Generating server TLS certificate...")
    srv_key, srv_cert = build_server_cert(ca_key, ca_cert, args.server_cn, args.sans)
    save_key(srv_key, out / "server.key")
    save_cert(srv_cert, out / "server.crt")

    print("\nDone! Next steps:")
    print("  1. Copy certs/ca.crt to each agent as the trust anchor")
    print("  2. Set CA_KEY_ENCRYPTION_KEY in .env (Fernet key)")
    print("  3. docker-compose up")


if __name__ == "__main__":
    main()
