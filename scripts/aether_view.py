#!/usr/bin/env python3
"""
AetherEdge Web UI — Streamlit dashboard for the Orchestrator.

Usage:
    streamlit run scripts/aether_view.py
"""
from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from orchestrator.database import SessionLocal
from orchestrator.models import Node, Task

REGISTRY_DIR = Path(__file__).resolve().parent.parent / "orchestrator" / "registry"
BLUEPRINTS_DIR = Path(__file__).resolve().parent.parent / "orchestrator" / "blueprints"
HEARTBEAT_ONLINE_THRESHOLD = 60  # seconds

st.set_page_config(page_title="AetherEdge", page_icon="⬡", layout="wide")
st.title("⬡ AetherEdge Orchestrator")


# ── Data helpers ──────────────────────────────────────────────────────────────

def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@st.cache_data(ttl=5)
def load_nodes() -> list[dict]:
    db = SessionLocal()
    try:
        nodes = db.query(Node).order_by(Node.registered_at.desc()).all()
        now = datetime.now(timezone.utc)
        rows = []
        for n in nodes:
            last_seen = n.last_seen_at
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)
            age = (now - last_seen).total_seconds()
            live = age <= HEARTBEAT_ONLINE_THRESHOLD
            rows.append({
                "node_id": n.node_id,
                "name": n.name or "—",
                "hostname": n.hostname,
                "platform": n.platform,
                "arch": n.arch,
                "status": "🟢 ONLINE" if live else "🔴 OFFLINE",
                "revoked": "Yes" if n.is_revoked else "No",
                "last_seen": last_seen.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "_node_id_raw": n.node_id,
            })
        return rows
    finally:
        db.close()


@st.cache_data(ttl=5)
def load_tasks() -> list[dict]:
    db = SessionLocal()
    try:
        tasks = db.query(Task).order_by(Task.created_at.desc()).all()
        rows = []
        for t in tasks:
            rows.append({
                "task_id": t.id[:8] + "…",
                "task_id_full": t.id,
                "node_id": (t.node_id or "")[:8] + "…" if t.node_id else "—",
                "script_name": t.script_name,
                "status": t.status,
                "result": t.result,
                "created_at": t.created_at.strftime("%Y-%m-%d %H:%M:%S UTC") if t.created_at else "—",
                "updated_at": t.updated_at.strftime("%Y-%m-%d %H:%M:%S UTC") if t.updated_at else "—",
            })
        return rows
    finally:
        db.close()


def get_registry_scripts() -> list[str]:
    if not REGISTRY_DIR.exists():
        return []
    return sorted(p.name for p in REGISTRY_DIR.glob("*.py"))


def get_blueprint_files() -> list[str]:
    if not BLUEPRINTS_DIR.exists():
        return []
    return sorted(p.name for p in BLUEPRINTS_DIR.glob("*.y*ml"))


def create_task(node_id: str, script_name: str, workload_type: str = "script") -> str:
    db = SessionLocal()
    try:
        task = Task(
            id=str(uuid.uuid4()),
            node_id=node_id,
            script_name=script_name,
            status="PENDING",
            workload_type=workload_type,
        )
        db.add(task)
        db.commit()
        return task.id
    finally:
        db.close()


# ── Overview metrics ──────────────────────────────────────────────────────────

nodes = load_nodes()
tasks = load_tasks()

total_nodes = len(nodes)
online_nodes = sum(1 for n in nodes if "ONLINE" in n["status"])
active_tasks = sum(1 for t in tasks if t["status"] in ("PENDING", "RUNNING"))
completed_tasks = sum(1 for t in tasks if t["status"] == "COMPLETED")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Nodes", total_nodes)
col2.metric("Online Nodes", online_nodes)
col3.metric("Active Tasks", active_tasks)
col4.metric("Completed Tasks", completed_tasks)

st.divider()


# ── Node table ────────────────────────────────────────────────────────────────

st.subheader("Nodes")

if nodes:
    display_cols = ["status", "name", "node_id", "hostname", "platform", "arch", "revoked", "last_seen"]
    df_nodes = pd.DataFrame(nodes)[display_cols]
    st.dataframe(df_nodes, width="stretch", hide_index=True)
else:
    st.info("No nodes registered yet.")

st.divider()


# ── Task log ──────────────────────────────────────────────────────────────────

st.subheader("Task Log")

status_filter = st.selectbox(
    "Filter by status",
    ["ALL", "PENDING", "RUNNING", "COMPLETED", "FAILED"],
    index=0,
)

filtered_tasks = tasks if status_filter == "ALL" else [t for t in tasks if t["status"] == status_filter]

if filtered_tasks:
    for t in filtered_tasks:
        status_icon = {"PENDING": "🟡", "RUNNING": "🔵", "COMPLETED": "🟢", "FAILED": "🔴"}.get(t["status"], "⚪")
        label = f"{status_icon} {t['status']}  |  {t['script_name']}  |  id: {t['task_id']}  |  {t['created_at']}"
        with st.expander(label):
            st.write(f"**Node:** {t['node_id']}")
            st.write(f"**Updated:** {t['updated_at']}")
            if t["result"]:
                st.write("**Result:**")
                try:
                    parsed = json.loads(t["result"])
                    st.json(parsed)
                except (json.JSONDecodeError, TypeError):
                    st.code(t["result"])
            else:
                st.write("_No result yet._")
else:
    st.info("No tasks found.")

st.divider()


# ── Sidebar: Control Panel ────────────────────────────────────────────────────

st.sidebar.header("Control Panel")
st.sidebar.subheader("Deploy Task")

online_node_list = [n for n in nodes if "ONLINE" in n["status"]]
scripts = get_registry_scripts()

if not online_node_list:
    st.sidebar.warning("No online nodes available.")
else:
    node_options = {
        f"{n['name']} ({n['node_id'][:8]}…)": n["_node_id_raw"]
        for n in online_node_list
    }
    selected_labels = st.sidebar.multiselect("Select Nodes", list(node_options.keys()), default=list(node_options.keys())[:1])
    selected_node_ids = [node_options[l] for l in selected_labels]

    workload_type = st.sidebar.radio("Workload Type", ["script", "blueprint"], horizontal=True)

    if workload_type == "script":
        options = get_registry_scripts()
        file_label = "Select Script"
    else:
        options = get_blueprint_files()
        file_label = "Select Blueprint"

    if not options:
        st.sidebar.warning(f"No {workload_type} files found.")
    else:
        selected_file = st.sidebar.selectbox(file_label, options)

        if st.sidebar.button("Deploy Task", width="stretch"):
            if not selected_node_ids:
                st.sidebar.warning("Select at least one node.")
            else:
                for node_id in selected_node_ids:
                    create_task(node_id, selected_file, workload_type)
                st.sidebar.success(f"Task deployed to {len(selected_node_ids)} node(s)!")
                st.cache_data.clear()
                st.rerun()

st.sidebar.divider()
st.sidebar.caption("Auto-refreshes every 5s via cache TTL. Use the button to force refresh.")

if st.sidebar.button("🔄 Refresh Now", width="stretch"):
    st.cache_data.clear()
    st.rerun()

# Auto-rerun every 5 seconds
import time
time.sleep(5)
st.rerun()
