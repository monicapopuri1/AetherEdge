from __future__ import annotations

import datetime
import os
import stat
from pathlib import Path

import requests as http_requests
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.x509.oid import NameOID


# ── Legacy self-signed cert (Ed25519) — kept for tests / offline fallback ─────

def generate_self_signed_cert(
    node_id: str,
    private_key_pem: str,
    certs_dir: str | Path,
) -> tuple[Path, Path]:
    certs_dir = Path(certs_dir)
    certs_dir.mkdir(parents=True, exist_ok=True)

    cert_path = certs_dir / "client.crt"
    key_path = certs_dir / "client.key"

    private_key = load_pem_private_key(private_key_pem.encode(), password=None)
    now = datetime.datetime.now(datetime.timezone.utc)

    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, node_id)]))
        .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, node_id)]))
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(node_id)]), critical=False)
        .sign(private_key, algorithm=None)  # Ed25519 requires algorithm=None
    )

    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    os.chmod(cert_path, 0o644)

    key_path.write_bytes(
        private_key.private_bytes(serialization.Encoding.PEM,
                                   serialization.PrivateFormat.PKCS8,
                                   serialization.NoEncryption())
    )
    os.chmod(key_path, 0o600)
    return cert_path, key_path


def get_or_create_certs(
    node_id: str,
    private_key_pem: str,
    certs_dir: str | Path = None,
) -> tuple[Path, Path]:
    if certs_dir is None:
        certs_dir = Path.home() / ".aetheredge" / "certs"
    certs_dir = Path(certs_dir)
    cert_path = certs_dir / "client.crt"
    key_path = certs_dir / "client.key"
    if cert_path.exists() and key_path.exists():
        return cert_path, key_path
    cert_path, key_path = generate_self_signed_cert(node_id, private_key_pem, certs_dir)
    print(f"[INFO] TLS certificates generated at {certs_dir}/")
    return cert_path, key_path


# ── CA-signed mTLS certs (RSA-2048) ──────────────────────────────────────────

def _generate_rsa_key(key_path: Path) -> rsa.RSAPrivateKey:
    """Generate RSA-2048 private key and persist to disk with restricted permissions."""
    certs_dir = key_path.parent
    certs_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(certs_dir, 0o700)  # rwx for owner only — no group/world access

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_path.write_bytes(
        private_key.private_bytes(serialization.Encoding.PEM,
                                   serialization.PrivateFormat.PKCS8,
                                   serialization.NoEncryption())
    )
    os.chmod(key_path, 0o600)  # rw for owner only
    return private_key


def check_key_permissions(key_path: Path) -> None:
    """
    Startup security check: refuse to run if the private key is world-readable.
    A world-readable key (mode & 0o004) means any local user can read the secret.
    Raises SystemExit so the node never starts in an insecure state.
    """
    if not key_path.exists():
        return  # Key not yet generated — nothing to check

    mode = stat.S_IMODE(os.stat(key_path).st_mode)

    if mode & 0o004:  # world-readable bit set
        print(
            f"\n[SECURITY ERROR] Private key {key_path} is world-readable "
            f"(current mode: {oct(mode)}).\n"
            f"Fix with:  chmod 0600 {key_path}\n"
            f"Refusing to start until permissions are corrected.\n",
            flush=True,
        )
        raise SystemExit(1)

    if mode & 0o040:  # group-readable — warn but don't block
        print(
            f"[SECURITY WARNING] Private key {key_path} is group-readable "
            f"(current mode: {oct(mode)}). Recommend: chmod 0600 {key_path}",
            flush=True,
        )


def _generate_csr(node_id: str, private_key) -> str:
    """Generate a CSR PEM from an RSA private key."""
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, node_id)]))
        .sign(private_key, hashes.SHA256())  # RSA requires a hash; Ed25519 uses None
    )
    return csr.public_bytes(serialization.Encoding.PEM).decode()


def request_signed_cert(
    node_id: str,
    csr_pem: str,
    orchestrator_url: str,
    certs_dir: Path,
    bootstrap_url: str = "",
) -> tuple[Path, Path]:
    """
    POST CSR to orchestrator's bootstrap endpoint (plain HTTP) to get a CA-signed cert.
    Returns (cert_path, ca_cert_path).
    """
    base = bootstrap_url or orchestrator_url
    resp = http_requests.post(
        f"{base}/api/v1/auth/sign",
        json={"node_id": node_id, "csr_pem": csr_pem},
        verify=False,   # Bootstrap: CA cert not yet stored locally
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    cert_path = certs_dir / "client.crt"
    ca_cert_path = certs_dir / "ca.crt"

    cert_path.write_text(data["certificate_pem"])
    os.chmod(cert_path, 0o644)

    ca_cert_path.write_text(data["ca_cert_pem"])
    os.chmod(ca_cert_path, 0o644)

    return cert_path, ca_cert_path


def cert_expires_within_days(cert_path: Path, days: int = 30) -> bool:
    """Return True if the certificate at cert_path expires within `days` days."""
    if not cert_path.exists():
        return False
    try:
        from cryptography import x509 as _x509
        cert = _x509.load_pem_x509_certificate(cert_path.read_bytes())
        expiry = cert.not_valid_after_utc
        remaining = (expiry - datetime.datetime.now(datetime.timezone.utc)).days
        return remaining <= days
    except Exception:
        return False


def renew_mtls_cert(
    node_id: str,
    orchestrator_url: str,
    certs_dir: Path,
    bootstrap_url: str = "",
) -> tuple[Path, Path]:
    """
    Force-renew the CA-signed client certificate by generating a new CSR and
    requesting a fresh signing from the orchestrator. Returns (cert_path, ca_cert_path).
    Existing key is reused so the node identity stays stable.
    """
    key_path = certs_dir / "client.key"
    if not key_path.exists():
        raise FileNotFoundError(f"Key not found at {key_path} — cannot renew cert.")
    private_key = load_pem_private_key(key_path.read_bytes(), password=None)
    csr_pem = _generate_csr(node_id, private_key)
    return request_signed_cert(node_id, csr_pem, orchestrator_url, certs_dir, bootstrap_url)


def get_or_create_mtls_certs(
    node_id: str,
    orchestrator_url: str,
    certs_dir: str | Path = None,
    bootstrap_url: str = "",
) -> tuple[Path, Path, Path]:
    """
    Idempotent mTLS cert acquisition.
    Returns (cert_path, key_path, ca_cert_path).

    First run:  generates RSA-2048 key → CSR → orchestrator signs it → stores cert + CA cert
    Subsequent: returns existing paths unchanged
    """
    if certs_dir is None:
        certs_dir = Path.home() / ".aetheredge" / "certs"
    certs_dir = Path(certs_dir)

    cert_path = certs_dir / "client.crt"
    key_path = certs_dir / "client.key"
    ca_cert_path = certs_dir / "ca.crt"

    if cert_path.exists() and key_path.exists() and ca_cert_path.exists():
        return cert_path, key_path, ca_cert_path

    certs_dir.mkdir(parents=True, exist_ok=True)
    print(f"[INFO] Requesting CA-signed mTLS certificate from orchestrator...")

    # Load or generate RSA key
    if key_path.exists():
        private_key = load_pem_private_key(key_path.read_bytes(), password=None)
    else:
        private_key = _generate_rsa_key(key_path)

    csr_pem = _generate_csr(node_id, private_key)
    cert_path, ca_cert_path = request_signed_cert(node_id, csr_pem, orchestrator_url, certs_dir, bootstrap_url)

    print(f"[INFO] mTLS certificate stored at {certs_dir}/")
    return cert_path, key_path, ca_cert_path
