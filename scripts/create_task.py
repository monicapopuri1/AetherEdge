#!/usr/bin/env python3
"""Manually insert a PENDING task into the AetherEdge tasks table.

Usage:
    python scripts/create_task.py <node_id> <script_name>

Example:
    python scripts/create_task.py abc123 maintenance_agent.py
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator.database import SessionLocal
from orchestrator.models import Node, Task


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: python scripts/create_task.py <node_id> <script_name>")
        sys.exit(1)

    node_id = sys.argv[1]
    script_name = sys.argv[2]

    db = SessionLocal()
    try:
        node = db.get(Node, node_id)
        if not node:
            print(f"Error: node '{node_id}' not found in the database.")
            sys.exit(1)

        if node.is_revoked:
            print(f"Warning: node '{node_id}' is revoked. Creating task anyway.")

        task = Task(
            id=str(uuid.uuid4()),
            node_id=node_id,
            script_name=script_name,
            status="PENDING",
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        print(f"Task created successfully.")
        print(f"  task_id    : {task.id}")
        print(f"  node_id    : {task.node_id}")
        print(f"  script_name: {task.script_name}")
        print(f"  status     : {task.status}")
        print(f"  created_at : {task.created_at}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
