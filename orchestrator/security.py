from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from ipaddress import IPv4Address
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.x509.oid import NameOID

log = logging.getLogger("aether.security")

_CA_DIR = Path.home() / ".aetheredge" / "ca"


class SecurityManager:
    def __init__(self, ca_dir: Path = None):
        self.ca_dir = Path(ca_dir) if ca_dir else _CA_DIR
        self.ca_cert_path = self.ca_dir / "ca.crt"
        self.ca_key_path = self.ca_dir / "ca.key"
        self.server_cert_path = self.ca_dir / "server.crt"
        self.server_key_path = self.ca_dir / "server.key"

    # ── Root CA ───────────────────────────────────────────────────────────────

    def ensure_ca(self) -> tuple[Path, Path]:
        """Generate a self-signed Root CA on first run."""
        if self.ca_cert_path.exists() and self.ca_key_path.exists():
            log.info("Root CA already exists at %s", self.ca_dir)
            return self.ca_cert_path, self.ca_key_path

        log.info("Generating AetherEdge Root CA (RSA-4096)...")
        self.ca_dir.mkdir(parents=True, exist_ok=True)

        ca_key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
        now = datetime.now(timezone.utc)
        name = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "AetherEdge Root CA"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "AetherEdge"),
        ])

        ca_cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(ca_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True, key_cert_sign=True, crl_sign=True,
                    content_commitment=False, key_encipherment=False,
                    data_encipherment=False, key_agreement=False,
                    encipher_only=False, decipher_only=False,
                ),
                critical=True,
            )
            .sign(ca_key, hashes.SHA256())
        )

        self.ca_key_path.write_bytes(
            ca_key.private_bytes(serialization.Encoding.PEM,
                                 serialization.PrivateFormat.PKCS8,
                                 serialization.NoEncryption())
        )
        os.chmod(self.ca_key_path, 0o600)

        self.ca_cert_path.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
        os.chmod(self.ca_cert_path, 0o644)

        log.info("Root CA generated: %s", self.ca_cert_path)
        return self.ca_cert_path, self.ca_key_path

    # ── Server cert ───────────────────────────────────────────────────────────

    def ensure_server_cert(self) -> tuple[Path, Path]:
        """Generate orchestrator TLS server cert signed by our CA."""
        if self.server_cert_path.exists() and self.server_key_path.exists():
            return self.server_cert_path, self.server_key_path

        log.info("Generating orchestrator server certificate (RSA-2048)...")
        ca_key = load_pem_private_key(self.ca_key_path.read_bytes(), password=None)
        ca_cert = x509.load_pem_x509_certificate(self.ca_cert_path.read_bytes())

        server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = datetime.now(timezone.utc)

        server_cert = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([
                x509.NameAttribute(NameOID.COMMON_NAME, "orchestrator.aetheredge.local"),
            ]))
            .issuer_name(ca_cert.subject)
            .public_key(server_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + timedelta(days=825))  # ~2 years, browser-compatible
            .add_extension(
                x509.SubjectAlternativeName([
                    x509.DNSName("localhost"),
                    x509.DNSName("orchestrator.aetheredge.local"),
                    x509.IPAddress(IPv4Address("127.0.0.1")),
                ]),
                critical=False,
            )
            .sign(ca_key, hashes.SHA256())
        )

        self.server_key_path.write_bytes(
            server_key.private_bytes(serialization.Encoding.PEM,
                                     serialization.PrivateFormat.PKCS8,
                                     serialization.NoEncryption())
        )
        os.chmod(self.server_key_path, 0o600)
        self.server_cert_path.write_bytes(server_cert.public_bytes(serialization.Encoding.PEM))
        os.chmod(self.server_cert_path, 0o644)

        log.info("Server certificate generated: %s", self.server_cert_path)
        return self.server_cert_path, self.server_key_path

    # ── CSR signing ───────────────────────────────────────────────────────────

    def sign_csr(self, csr_pem: str, node_id: str) -> str:
        """Sign a node CSR. Injects localhost SANs so local tests don't break."""
        ca_key = load_pem_private_key(self.ca_key_path.read_bytes(), password=None)
        ca_cert = x509.load_pem_x509_certificate(self.ca_cert_path.read_bytes())
        csr = x509.load_pem_x509_csr(csr_pem.encode())

        now = datetime.now(timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(csr.subject)
            .issuer_name(ca_cert.subject)
            .public_key(csr.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + timedelta(days=365))
            .add_extension(
                x509.SubjectAlternativeName([
                    x509.DNSName(node_id),
                    x509.DNSName("localhost"),
                    x509.IPAddress(IPv4Address("127.0.0.1")),
                ]),
                critical=False,
            )
            .add_extension(
                x509.ExtendedKeyUsage([x509.ExtendedKeyUsageOID.CLIENT_AUTH]),
                critical=False,
            )
            .sign(ca_key, hashes.SHA256())
        )
        return cert.public_bytes(serialization.Encoding.PEM).decode()

    def get_ca_cert_pem(self) -> str:
        return self.ca_cert_path.read_text()


# Module-level singleton
_instance: SecurityManager | None = None


def get_security_manager() -> SecurityManager:
    global _instance
    if _instance is None:
        _instance = SecurityManager()
    return _instance
