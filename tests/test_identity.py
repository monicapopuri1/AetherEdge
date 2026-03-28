import json
import os
import stat
import tempfile
from pathlib import Path

import pytest

from aetheredge.identity import (
    _derive_node_id,
    _generate_keypair,
    _get_hardware_fingerprint,
    _save_identity,
    get_or_create_identity,
)


def test_hardware_fingerprint_keys():
    hw = _get_hardware_fingerprint()
    assert set(hw.keys()) == {"hostname", "mac_address", "machine_id", "platform", "arch"}
    assert hw["hostname"]
    assert hw["mac_address"].startswith("0x")


def test_generate_keypair_returns_pem():
    private_pem, public_pem = _generate_keypair()
    assert "BEGIN PRIVATE KEY" in private_pem
    assert "BEGIN PUBLIC KEY" in public_pem


def test_derive_node_id_format():
    private_pem, _ = _generate_keypair()
    hw = _get_hardware_fingerprint()
    node_id = _derive_node_id(hw, private_pem)
    assert node_id.startswith("aether-")
    # 7 chars prefix + 32 hex chars
    assert len(node_id) == 7 + 32
    assert all(c in "0123456789abcdef" for c in node_id[7:])


def test_derive_node_id_deterministic():
    private_pem, _ = _generate_keypair()
    hw = _get_hardware_fingerprint()
    id1 = _derive_node_id(hw, private_pem)
    id2 = _derive_node_id(hw, private_pem)
    assert id1 == id2


def test_save_identity_permissions():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "identity.json"
        data = {"node_id": "aether-test", "schema_version": "1.0"}
        _save_identity(path, data)
        assert path.exists()
        mode = stat.S_IMODE(os.stat(path).st_mode)
        assert mode == 0o600
        loaded = json.loads(path.read_text())
        assert loaded["node_id"] == "aether-test"


def test_get_or_create_identity_creates_file():
    with tempfile.TemporaryDirectory() as tmp:
        identity_path = Path(tmp) / "identity.json"
        identity = get_or_create_identity(identity_path)
        assert identity["node_id"].startswith("aether-")
        assert identity_path.exists()
        assert "public_key_pem" in identity
        assert "private_key_pem" in identity
        assert "hardware" in identity


def test_get_or_create_identity_idempotent():
    with tempfile.TemporaryDirectory() as tmp:
        identity_path = Path(tmp) / "identity.json"
        id1 = get_or_create_identity(identity_path)
        id2 = get_or_create_identity(identity_path)
        assert id1["node_id"] == id2["node_id"]
        assert id1["created_at"] == id2["created_at"]
