#!/usr/bin/env python3
"""Remove OFFLINE nodes from the AetherEdge database.

Usage:
    python3 scripts/remove_offline_nodes.py           # preview (dry run)
    python3 scripts/remove_offline_nodes.py --confirm  # actually delete
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator.database import SessionLocal
from orchestrator.models import Node


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove OFFLINE nodes from the database.")
    parser.add_argument(
        "--confirm", action="store_true",
        help="Actually delete the nodes (default is dry run)."
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        offline = db.query(Node).filter(Node.status == "OFFLINE").all()

        if not offline:
            print("No offline nodes found.")
            return

        print(f"{'DRY RUN — ' if not args.confirm else ''}Found {len(offline)} offline node(s):\n")
        for n in offline:
            print(f"  {n.node_id}  hostname={n.hostname}  last_seen={str(n.last_seen_at)[:19]}")

        if not args.confirm:
            print("\nRun with --confirm to delete them.")
            return

        for n in offline:
            db.delete(n)
        db.commit()
        print(f"\nDeleted {len(offline)} offline node(s).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
