#!/usr/bin/env python3
"""List all nodes with their ID, name, and status.

Usage:
    python3 scripts/list_nodes.py
    python3 scripts/list_nodes.py --online    # only ONLINE nodes
    python3 scripts/list_nodes.py --offline   # only OFFLINE nodes
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator.database import SessionLocal
from orchestrator.models import Node


def main() -> None:
    parser = argparse.ArgumentParser(description="List nodes and their status.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--online", action="store_true", help="Show only ONLINE nodes.")
    group.add_argument("--offline", action="store_true", help="Show only OFFLINE nodes.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        q = db.query(Node)
        if args.online:
            q = q.filter(Node.status == "ONLINE")
        elif args.offline:
            q = q.filter(Node.status == "OFFLINE")

        nodes = q.order_by(Node.registered_at.desc()).all()

        if not nodes:
            print("No nodes found.")
            return

        print(f"{'NODE ID':<40} {'NAME':<20} {'STATUS'}")
        print("─" * 70)
        for n in nodes:
            print(f"{n.node_id:<40} {(n.name or '—'):<20} {n.status}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
