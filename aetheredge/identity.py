from __future__ import annotations

import hashlib
import json
import os
import platform
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import psutil

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _get_hardware_fingerprint() -> dict:
    hostname = platform.node()
    mac_address = hex(uuid.getnode())

    machine_id_path = Path("/etc/machine-id")
    if machine_id_path.exists():
        machine_id = machine_id_path.read_text().strip()
    else:
        machine_id = platform.node()

    return {
        "hostname": hostname,
        "mac_address": mac_address,
        "machine_id": machine_id,
        "platform": platform.system(),
        "arch": platform.machine(),
    }


def get_system_specs() -> dict:
    """Collect live system specs — called at registration time, not stored in identity.json."""
    ram_bytes = psutil.virtual_memory().total
    ram_gb = round(ram_bytes / (1024 ** 3), 1)
    return {
        "cpu_count": os.cpu_count() or 0,
        "cpu_model": platform.processor() or platform.machine(),
        "ram_total_gb": ram_gb,
        "os_version": platform.version(),
    }


def _generate_keypair() -> tuple[str, str]:
    private_key = Ed25519PrivateKey.generate()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()

    return private_pem, public_pem


def _derive_node_id(hardware: dict, private_key_pem: str, name: str = "") -> str:
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    private_key = load_pem_private_key(private_key_pem.encode(), password=None)
    public_key = private_key.public_key()

    raw_public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    pubkey_hex = raw_public_bytes.hex()

    hostname = hardware["hostname"]
    mac_address = hardware["mac_address"]
    machine_id = hardware["machine_id"]
    # name is mixed into the hash so each named instance gets a truly distinct ID
    hardware_str = f"{hostname}:{mac_address}:{machine_id}:{name}"

    digest = hashlib.sha256((hardware_str + pubkey_hex).encode()).hexdigest()
    return f"aether-{digest[:32]}"


def _save_identity(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
    os.chmod(path, 0o600)


def get_or_create_identity(identity_path: str | Path = None, name: str = "") -> dict:
    if identity_path is None:
        base = Path.home() / ".aetheredge"
        filename = f"identity-{name}.json" if name else "identity.json"
        identity_path = base / filename

    identity_path = Path(identity_path)

    if identity_path.exists():
        data = json.loads(identity_path.read_text())
        return data

    label = f" [{name}]" if name else ""
    print(f"[INFO] Generating new identity{label}...")

    hardware = _get_hardware_fingerprint()
    private_pem, public_pem = _generate_keypair()
    node_id = _derive_node_id(hardware, private_pem, name=name)

    identity = {
        "schema_version": "1.0",
        "node_id": node_id,
        "name": name or None,
        "public_key_pem": public_pem,
        "private_key_pem": private_pem,
        "hardware": hardware,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }

    _save_identity(identity_path, identity)
    print(f"[INFO] Node identity saved to {identity_path}")

    return identity
