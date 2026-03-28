from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class AetherConfig:
    orchestrator_url: str   # mTLS port (https, CERT_REQUIRED)
    bootstrap_url: str      # plain-HTTP port for /register and /auth/sign
    listen_port: int
    ca_cert_path: Optional[str]
    log_level: str


_config_singleton: Optional[AetherConfig] = None


def load_config(config_path: str | Path = "config/config.yaml") -> AetherConfig:
    global _config_singleton
    if _config_singleton is not None:
        return _config_singleton

    with open(config_path, "r") as f:
        raw = yaml.safe_load(f) or {}

    orchestrator_url = os.environ.get("AETHER_ORCHESTRATOR_URL", raw.get("orchestrator_url", "https://orchestrator.aetheredge.local"))

    try:
        listen_port = int(os.environ.get("AETHER_PORT", raw.get("listen_port", 7331)))
    except (ValueError, TypeError):
        raise ValueError(f"Invalid listen_port value: {os.environ.get('AETHER_PORT', raw.get('listen_port'))}")

    if not (1024 <= listen_port <= 65535):
        raise ValueError(f"listen_port must be in range 1024–65535, got {listen_port}")

    bootstrap_url = os.environ.get(
        "AETHER_BOOTSTRAP_URL",
        raw.get("bootstrap_url", "http://localhost:8000"),
    )
    ca_cert_path = raw.get("ca_cert_path", None)
    log_level = raw.get("log_level", "INFO")

    _config_singleton = AetherConfig(
        orchestrator_url=orchestrator_url,
        bootstrap_url=bootstrap_url,
        listen_port=listen_port,
        ca_cert_path=ca_cert_path,
        log_level=log_level,
    )
    return _config_singleton


def _reset_config_cache() -> None:
    """Reset singleton — used in tests."""
    global _config_singleton
    _config_singleton = None
