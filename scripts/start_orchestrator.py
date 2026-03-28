#!/usr/bin/env python3
"""
Start AetherOrchestrator with full mTLS (CERT_REQUIRED) + a plain-HTTP bootstrap server.

Why two ports?
  ssl.CERT_REQUIRED means the TLS handshake itself rejects connections with no
  client certificate — before FastAPI even sees the request.  Bootstrap endpoints
  (/register, /auth/sign) must be reachable by nodes that don't have a cert yet,
  so they run on a separate plain-HTTP port.

  Port layout (defaults):
    8001  HTTPS + CERT_REQUIRED  — mTLS-only: heartbeat, tasks, workloads
    8000  HTTP (no TLS)          — bootstrap: /register, /auth/sign

Usage:
    python3 scripts/start_orchestrator.py
    python3 scripts/start_orchestrator.py --port 8001 --bootstrap-port 8000
"""
from __future__ import annotations

import argparse
import asyncio
import ssl
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn
from uvicorn.protocols.http.h11_impl import H11Protocol

from orchestrator.security import SecurityManager


class MTLSProtocol(H11Protocol):
    """
    Injects the TLS peer certificate into the ASGI request scope so FastAPI
    dependencies can read it via request.scope["ssl_client_cert"].

    uvicorn 0.30 removed handle(); the correct hook is handle_events(), which
    is called synchronously for each inbound HTTP event.  super().handle_events()
    builds self.cycle (with its scope dict) and schedules the ASGI task — but
    the task hasn't started yet, so mutating the scope dict here is safe.

    Note: reload=True is NOT compatible with a custom http class.
    """

    def connection_made(self, transport: asyncio.Transport) -> None:
        super().connection_made(transport)
        ssl_obj = transport.get_extra_info("ssl_object")
        self._peer_cert: dict | None = ssl_obj.getpeercert() if ssl_obj else None

    def handle_events(self) -> None:
        super().handle_events()
        # Inject cert into the scope of the cycle that super() just created.
        # self.cycle is None until an h11.Request event is processed.
        if getattr(self, "cycle", None) is not None:
            self.cycle.scope["ssl_client_cert"] = self._peer_cert


async def _serve_all(
    host: str,
    mtls_port: int,
    bootstrap_port: int,
    server_cert: Path,
    server_key: Path,
    ca_cert: Path,
) -> None:
    # ── mTLS server (CERT_REQUIRED — the Bouncer) ─────────────────────────────
    mtls_config = uvicorn.Config(
        "orchestrator.main:app",
        host=host,
        port=mtls_port,
        ssl_keyfile=str(server_key),
        ssl_certfile=str(server_cert),
        ssl_ca_certs=str(ca_cert),
        ssl_cert_reqs=ssl.CERT_REQUIRED,   # TLS handshake rejects no-cert connections
        http=MTLSProtocol,
        log_level="info",
    )

    # ── Bootstrap server (plain HTTP — no client cert required) ───────────────
    bootstrap_config = uvicorn.Config(
        "orchestrator.main:app",
        host=host,
        port=bootstrap_port,
        log_level="info",
    )

    mtls_server = uvicorn.Server(mtls_config)
    bootstrap_server = uvicorn.Server(bootstrap_config)

    await asyncio.gather(
        mtls_server.serve(),
        bootstrap_server.serve(),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="AetherOrchestrator (mTLS + bootstrap)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001, dest="mtls_port",
                        help="mTLS port — CERT_REQUIRED (default: 8001)")
    parser.add_argument("--bootstrap-port", type=int, default=8000,
                        help="Plain-HTTP bootstrap port for /register and /auth/sign (default: 8000)")
    args = parser.parse_args()

    security = SecurityManager()
    security.ensure_ca()
    server_cert, server_key = security.ensure_server_cert()

    print(f"\n{'─' * 58}")
    print(f"  AetherOrchestrator")
    print(f"{'─' * 58}")
    print(f"  mTLS   (CERT_REQUIRED) : https://{args.host}:{args.mtls_port}")
    print(f"  Bootstrap (plain HTTP) :  http://{args.host}:{args.bootstrap_port}")
    print(f"  CA cert                : {security.ca_cert_path}")
    print(f"  Server cert            : {server_cert}")
    print(f"{'─' * 58}\n")

    asyncio.run(_serve_all(
        host=args.host,
        mtls_port=args.mtls_port,
        bootstrap_port=args.bootstrap_port,
        server_cert=server_cert,
        server_key=server_key,
        ca_cert=security.ca_cert_path,
    ))


if __name__ == "__main__":
    main()
