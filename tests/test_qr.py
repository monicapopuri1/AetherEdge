import re

from aetheredge.qr import _get_local_ip, build_connection_url


def test_get_local_ip_returns_string():
    ip = _get_local_ip()
    assert isinstance(ip, str)
    assert len(ip) > 0


def test_get_local_ip_valid_format():
    ip = _get_local_ip()
    # Either a valid IPv4 or the fallback
    parts = ip.split(".")
    assert len(parts) == 4
    assert all(p.isdigit() for p in parts)


def test_build_connection_url_format():
    node_id = "aether-864c9962ca352113441987f1ad7d3b31"
    url = build_connection_url(node_id, 7331)
    pattern = r"^aether://" + re.escape(node_id) + r"@\d+\.\d+\.\d+\.\d+:7331$"
    assert re.match(pattern, url), f"URL did not match expected pattern: {url}"


def test_build_connection_url_uses_port():
    node_id = "aether-864c9962ca352113441987f1ad7d3b31"
    url = build_connection_url(node_id, 9000)
    assert url.endswith(":9000")
