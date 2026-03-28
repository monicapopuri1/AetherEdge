from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

import requests
from rich.console import Console

from aetheredge.identity import get_system_specs

if TYPE_CHECKING:
    from aetheredge.config import AetherConfig

console = Console()


def _build_payload(identity: dict) -> dict:
    specs = get_system_specs()
    return {
        "node_id": identity["node_id"],
        "public_key_pem": identity["public_key_pem"],
        "hardware_metadata": {
            "hostname": identity["hardware"]["hostname"],
            "mac_address": identity["hardware"]["mac_address"],
            "machine_id": identity["hardware"]["machine_id"],
            "platform": identity["hardware"]["platform"],
            "arch": identity["hardware"]["arch"],
            "cpu_count": specs["cpu_count"],
            "cpu_model": specs["cpu_model"],
            "ram_total_gb": specs["ram_total_gb"],
            "os_version": specs["os_version"],
        },
        "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def _simulate_orchestrator_response(node_id: str) -> dict:
    return {
        "status": "registered",
        "node_id": node_id,
        "message": "STUB: Orchestrator not deployed. Simulated registration.",
        "assigned_cluster": "edge-cluster-alpha",
        "heartbeat_interval_seconds": 30,
    }


def register_with_orchestrator(
    identity: dict,
    cert_path,
    key_path,
    config: "AetherConfig",
) -> dict:
    node_id = identity["node_id"]
    payload = _build_payload(identity)
    # Use bootstrap_url (plain HTTP) — registration happens before the node has a cert,
    # so it cannot connect to the CERT_REQUIRED mTLS port.
    base = getattr(config, "bootstrap_url", config.orchestrator_url)
    endpoint = f"{base}/api/v1/nodes/register"

    console.log(f"[cyan]Registration target:[/cyan] {endpoint}")

    # Bootstrap endpoint is plain HTTP — no TLS verification needed
    verify = False
    try:
        response = requests.post(
            endpoint,
            json=payload,
            verify=verify,
            timeout=5,
        )
        response.raise_for_status()
        result = response.json()
        console.print(f"[green][INFO] Orchestrator response: {result}[/green]")
        return result
    except requests.exceptions.ConnectionError as exc:
        console.print(
            f"[bold red][ERROR] Cannot reach orchestrator at {endpoint}.[/bold red]\n"
            "[red]       Is the orchestrator running? Check: python3 scripts/start_orchestrator.py[/red]"
        )
        raise RuntimeError(
            f"Orchestrator unreachable at {endpoint}. Start the orchestrator first."
        ) from exc
    except requests.exceptions.HTTPError as e:
        console.print(f"[bold red][ERROR] Orchestrator returned error: {e}[/bold red]")
        raise
