#!/usr/bin/env python3
"""Pretty-print the AetherEdge SQLite database contents."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console
from rich.table import Table

from orchestrator.database import SessionLocal
from orchestrator.models import Node, Task

console = Console()


def show_nodes(db) -> None:
    nodes = db.query(Node).order_by(Node.registered_at.desc()).all()

    t = Table(title=f"Nodes ({len(nodes)})", show_lines=True)
    t.add_column("Node ID", style="cyan", no_wrap=True)
    t.add_column("Hostname")
    t.add_column("Platform")
    t.add_column("Arch")
    t.add_column("CPUs", justify="right")
    t.add_column("CPU Model")
    t.add_column("RAM (GB)", justify="right")
    t.add_column("OS Version", overflow="fold")
    t.add_column("Status", justify="center")
    t.add_column("Last Seen")

    for n in nodes:
        status_style = "green" if n.status == "ONLINE" else "red"
        t.add_row(
            n.node_id,
            n.hostname,
            n.platform,
            n.arch,
            str(n.cpu_count or "–"),
            n.cpu_model or "–",
            str(n.ram_total_gb or "–"),
            n.os_version or "–",
            f"[{status_style}]{n.status}[/{status_style}]",
            str(n.last_seen_at)[:19],
        )

    console.print(t)


def show_tasks(db) -> None:
    tasks = db.query(Task).order_by(Task.created_at.desc()).all()

    t = Table(title=f"Tasks ({len(tasks)})", show_lines=True)
    t.add_column("Task ID", style="cyan", no_wrap=True)
    t.add_column("Type")
    t.add_column("Status", justify="center")
    t.add_column("Assigned To")
    t.add_column("Created")
    t.add_column("Completed")

    status_colors = {"pending": "yellow", "assigned": "blue", "complete": "green"}
    for task in tasks:
        color = status_colors.get(task.status, "white")
        t.add_row(
            task.task_id[:8] + "…",
            task.type,
            f"[{color}]{task.status}[/{color}]",
            task.assigned_to or "–",
            str(task.created_at)[:19],
            str(task.completed_at)[:19] if task.completed_at else "–",
        )

    console.print(t)


def main() -> None:
    db = SessionLocal()
    try:
        show_nodes(db)
        console.print()
        show_tasks(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
