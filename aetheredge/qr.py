from __future__ import annotations

import socket

import qrcode.main
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console()


def _get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def build_connection_url(node_id: str, port: int) -> str:
    local_ip = _get_local_ip()
    return f"aether://{node_id}@{local_ip}:{port}"


def display_qr_and_identity(node_id: str, port: int) -> None:
    url = build_connection_url(node_id, port)

    qr = qrcode.main.QRCode(border=2)
    qr.add_data(url)
    qr.make(fit=True)
    qr.print_ascii(tty=False, invert=False)

    panel_content = Text()
    panel_content.append(f"Node ID: ", style="bold white")
    panel_content.append(node_id, style="bold cyan")

    console.print(Panel(panel_content, title="[bold]AetherEdge Node[/bold]", expand=False))
    console.print(f"[dim]Connection URL: {url}[/dim]")
    console.print(
        "\n[bold yellow]📱 Scan the QR code with your phone to claim this node.[/bold yellow]"
        "\n[dim]   Open your camera app and point it at the code above.[/dim]\n"
    )
