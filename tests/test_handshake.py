from unittest.mock import MagicMock, patch

from aetheredge.config import AetherConfig
from aetheredge.handshake import _build_payload, _simulate_orchestrator_response, register_with_orchestrator
from aetheredge.identity import _generate_keypair, _get_hardware_fingerprint, _derive_node_id


def _make_identity():
    hw = _get_hardware_fingerprint()
    private_pem, public_pem = _generate_keypair()
    node_id = _derive_node_id(hw, private_pem)
    return {
        "schema_version": "1.0",
        "node_id": node_id,
        "public_key_pem": public_pem,
        "private_key_pem": private_pem,
        "hardware": hw,
        "created_at": "2026-03-13T10:00:00Z",
    }


def test_build_payload_schema():
    identity = _make_identity()
    payload = _build_payload(identity)
    assert payload["node_id"] == identity["node_id"]
    assert payload["public_key_pem"] == identity["public_key_pem"]
    assert "hardware_metadata" in payload
    assert set(payload["hardware_metadata"].keys()) == {
        "hostname", "mac_address", "machine_id", "platform", "arch",
        "cpu_count", "cpu_model", "ram_total_gb", "os_version",
    }
    assert "timestamp_utc" in payload
    assert payload["timestamp_utc"].endswith("Z")


def test_simulate_orchestrator_response():
    resp = _simulate_orchestrator_response("aether-abc123")
    assert resp["status"] == "registered"
    assert resp["node_id"] == "aether-abc123"


def test_register_raises_when_orchestrator_unreachable():
    """Registration must fail loudly — not silently return a fake response."""
    identity = _make_identity()
    config = AetherConfig(
        orchestrator_url="https://orchestrator.aetheredge.local",
        bootstrap_url="http://localhost:8000",
        listen_port=7331,
        ca_cert_path=None,
        log_level="INFO",
    )
    import requests as _req
    with patch("aetheredge.handshake.requests.post", side_effect=_req.exceptions.ConnectionError):
        try:
            register_with_orchestrator(identity, "/tmp/client.crt", "/tmp/client.key", config)
            assert False, "Should have raised RuntimeError"
        except RuntimeError as exc:
            assert "unreachable" in str(exc).lower()
