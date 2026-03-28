#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
import warnings
from pathlib import Path
from time import monotonic

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
import urllib3
from rich.console import Console
from rich.panel import Panel

from aetheredge.certs import check_key_permissions, cert_expires_within_days, get_or_create_mtls_certs, renew_mtls_cert
from aetheredge.config import load_config
from aetheredge.handshake import register_with_orchestrator
from aetheredge.identity import get_or_create_identity
from aetheredge.qr import display_qr_and_identity
from aetheredge.runner import BlueprintRunner, WorkloadRunner

console = Console()

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config" / "config.yaml"
AETHER_DIR = Path.home() / ".aetheredge"
HEARTBEAT_INTERVAL = 5   # seconds
CERT_RENEW_DAYS = 30     # renew cert if expiring within this many days


def heartbeat_loop(node_id: str, orchestrator_url: str,
                   cert: tuple[str, str], ca_cert: str,
                   certs_dir: Path, config,
                   name: str = "") -> None:
    script_runner = WorkloadRunner(node_id, orchestrator_url, cert, ca_cert)
    blueprint_runner = BlueprintRunner(node_id, orchestrator_url, cert, ca_cert)
    console.print(
        f"\n[dim]Heartbeat active — polling every {HEARTBEAT_INTERVAL}s (mTLS). "
        "Ctrl+C to stop.[/dim]"
    )
    payload: dict = {"node_id": node_id}
    if name:
        payload["name"] = name
    while True:
        try:
            # ── Cert auto-renewal check ───────────────────────────────────────
            cert_path = certs_dir / "client.crt"
            if cert_expires_within_days(cert_path, CERT_RENEW_DAYS):
                console.print(
                    f"[yellow]Cert expires within {CERT_RENEW_DAYS} days — renewing...[/yellow]"
                )
                try:
                    new_cert_path, new_ca_path = renew_mtls_cert(
                        node_id=node_id,
                        orchestrator_url=config.orchestrator_url,
                        certs_dir=certs_dir,
                        bootstrap_url=config.bootstrap_url,
                    )
                    cert = (str(new_cert_path), cert[1])
                    ca_cert = str(new_ca_path)
                    script_runner.cert = cert
                    script_runner.ca_cert = ca_cert
                    blueprint_runner.cert = cert
                    blueprint_runner.ca_cert = ca_cert
                    console.print("[green]Cert renewed successfully.[/green]")
                except Exception as exc:
                    console.print(f"[red]Cert renewal failed: {exc}[/red]")

            resp = requests.post(
                f"{orchestrator_url}/api/v1/nodes/heartbeat",
                json=payload,
                cert=cert,
                verify=ca_cert,
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("action") == "EXECUTE":
                workload_type = data.get("workload_type", "script")
                if workload_type == "blueprint":
                    blueprint_runner.run(
                        task_id=data["task_id"],
                        blueprint_url=data["blueprint_url"],
                    )
                else:
                    script_runner.run(
                        task_id=data["task_id"],
                        script_url=data["script_url"],
                    )
            else:
                console.print("[dim]♡  heartbeat ok (mTLS) — no pending tasks[/dim]")

        except requests.exceptions.ConnectionError:
            console.print("[yellow]heartbeat: orchestrator unreachable, retrying...[/yellow]")
        except requests.exceptions.RequestException as e:
            console.print(f"[red]heartbeat error: {e}[/red]")

        time.sleep(HEARTBEAT_INTERVAL)


def main() -> None:
    _boot_start = monotonic()
    parser = argparse.ArgumentParser(description="AetherEdge Node Bootstrap")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--identity", type=Path, default=None,
                        help="Explicit path to identity JSON (overrides --name)")
    parser.add_argument("--name", type=str, default="",
                        help="Instance name for multi-node testing (e.g. --name worker1)")
    parser.add_argument("--reset-identity", action="store_true",
                        help="Delete existing identity file and generate a fresh one")
    args = parser.parse_args()

    name = args.name.strip()
    if args.identity is not None:
        identity_path = args.identity
    else:
        filename = f"identity-{name}.json" if name else "identity.json"
        identity_path = AETHER_DIR / filename

    certs_dir = AETHER_DIR / "nodes" / name / "certs" if name else AETHER_DIR / "certs"

    # ── Security pre-flight: refuse to start with a world-readable key ────────
    check_key_permissions(certs_dir / "client.key")

    if args.reset_identity and identity_path.exists():
        identity_path.unlink()
        console.print(f"[yellow]Identity reset: deleted {identity_path}[/yellow]")

    # ── Step 1: Config ────────────────────────────────────────────────────────
    config = load_config(args.config)

    # ── Step 2: Identity (Ed25519) ────────────────────────────────────────────
    identity = get_or_create_identity(identity_path, name=name)
    node_id = identity["node_id"]

    # ── Step 3: Register with orchestrator (no client cert yet) ──────────────
    # Registration must happen BEFORE cert signing — sign endpoint checks the DB.
    try:
        reg_result = register_with_orchestrator(identity, None, None, config)
    except RuntimeError as exc:
        console.print(f"\n[bold red]Bootstrap failed:[/bold red] {exc}")
        raise SystemExit(1)

    # ── Step 4: Get CA-signed mTLS cert ───────────────────────────────────────
    # Suppress InsecureRequestWarning for the bootstrap CSR POST (verify=False).
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    try:
        cert_path, key_path, ca_cert_path = get_or_create_mtls_certs(
            node_id=node_id,
            orchestrator_url=config.orchestrator_url,
            certs_dir=certs_dir,
            bootstrap_url=config.bootstrap_url,
        )
        mtls_available = True
    except Exception as exc:
        console.print(f"[yellow][WARNING] Could not get CA-signed cert: {exc}[/yellow]")
        console.print("[yellow]          Heartbeat will be skipped until orchestrator is reachable.[/yellow]")
        mtls_available = False
        cert_path = key_path = ca_cert_path = None

    # ── Step 5: QR + banner ───────────────────────────────────────────────────
    display_qr_and_identity(node_id, config.listen_port)

    boot_time = monotonic() - _boot_start
    boot_color = "green" if boot_time < 60 else "yellow"
    console.print(
        Panel(
            f"[bold green]Node bootstrap complete[/bold green]\n"
            f"Node ID   : [cyan]{node_id}[/cyan]\n"
            f"Cert      : {cert_path or '(unavailable)'}\n"
            f"CA cert   : {ca_cert_path or '(unavailable)'}\n"
            f"mTLS      : {'[green]enabled[/green]' if mtls_available else '[yellow]disabled (no orchestrator)[/yellow]'}\n"
            f"Status    : {reg_result.get('status', 'unknown')}\n"
            f"Boot time : [{boot_color}]{boot_time:.1f}s[/{boot_color}] "
            f"{'✓ under 60s' if boot_time < 60 else '⚠ exceeded 60s target'}",
            title="[bold]AetherEdge[/bold]",
            expand=False,
        )
    )

    # ── Step 6: Heartbeat loop ────────────────────────────────────────────────
    if mtls_available:
        heartbeat_loop(
            node_id=node_id,
            orchestrator_url=config.orchestrator_url,
            cert=(str(cert_path), str(key_path)),
            ca_cert=str(ca_cert_path),
            certs_dir=certs_dir,
            config=config,
            name=name,
        )
    else:
        console.print("[dim]Heartbeat disabled — start orchestrator and re-run to enable mTLS.[/dim]")


if __name__ == "__main__":
    main()
