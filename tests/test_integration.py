"""
Integration tests for AetherEdge.

Covers the full task lifecycle:
  node registration → task creation → heartbeat dispatch → result submission

Uses:
  - FastAPI TestClient with an isolated in-memory SQLite DB (StaticPool)
  - mTLS dependency overridden (no real certs needed)
  - No live orchestrator or node process required
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestrator.database import Base, get_db
from orchestrator.main import app
from orchestrator.mtls import require_unrevoked_cert


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def test_engine():
    """Single in-memory SQLite DB shared across all sessions in a test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,   # all sessions share one connection → same DB
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture()
def db_session(test_engine):
    """Direct DB session for test-side inserts/inspections."""
    Session = sessionmaker(bind=test_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def client(test_engine):
    """TestClient with the test DB and mTLS injected."""
    TestSession = sessionmaker(bind=test_engine)

    def _override_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    def _override_mtls():
        return {"CN": "test-node", "verified": True}

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_unrevoked_cert] = _override_mtls
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


def _register_payload(node_id: str) -> dict:
    return {
        "node_id": node_id,
        "public_key_pem": "-----BEGIN PUBLIC KEY-----\nMOCK\n-----END PUBLIC KEY-----",
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hardware_metadata": {
            "hostname": "test-host",
            "mac_address": "0xaabbccddee",
            "machine_id": "test-machine-id",
            "platform": "linux",
            "arch": "x86_64",
            "cpu_count": 4,
            "cpu_model": "Intel Test CPU",
            "ram_total_gb": 8.0,
            "os_version": "Ubuntu 22.04",
        },
    }


# ── Node registration ─────────────────────────────────────────────────────────

def test_node_registration(client):
    node_id = f"aether-{uuid.uuid4().hex[:32]}"
    resp = client.post("/api/v1/nodes/register", json=_register_payload(node_id))
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "registered"
    assert data["node_id"] == node_id


def test_node_re_registration_updates_record(client):
    node_id = f"aether-{uuid.uuid4().hex[:32]}"
    client.post("/api/v1/nodes/register", json=_register_payload(node_id))
    resp = client.post("/api/v1/nodes/register", json=_register_payload(node_id))
    assert resp.status_code == 200
    assert resp.json()["message"] == "Node re-registered successfully."


# ── Heartbeat ─────────────────────────────────────────────────────────────────

def test_heartbeat_no_pending_tasks(client):
    node_id = f"aether-{uuid.uuid4().hex[:32]}"
    client.post("/api/v1/nodes/register", json=_register_payload(node_id))
    resp = client.post("/api/v1/nodes/heartbeat", json={"node_id": node_id})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data.get("action") is None


# ── Full script task flow ─────────────────────────────────────────────────────

def test_full_script_task_flow(client, db_session):
    """Register → insert PENDING script task → heartbeat returns EXECUTE → submit result → COMPLETED."""
    from orchestrator.models import Task

    node_id = f"aether-{uuid.uuid4().hex[:32]}"
    client.post("/api/v1/nodes/register", json=_register_payload(node_id))

    task_id = str(uuid.uuid4())
    db_session.add(Task(
        id=task_id, node_id=node_id,
        script_name="maintenance_agent.py",
        status="PENDING", workload_type="script",
    ))
    db_session.commit()

    # Heartbeat should dispatch the task
    resp = client.post("/api/v1/nodes/heartbeat", json={"node_id": node_id})
    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "EXECUTE"
    assert data["task_id"] == task_id
    assert data["workload_type"] == "script"
    assert "maintenance_agent.py" in data["script_url"]

    # Task should now be RUNNING
    db_session.expire_all()
    task = db_session.get(Task, task_id)
    assert task.status == "RUNNING"

    # Submit result
    resp = client.post(
        f"/api/v1/tasks/{task_id}/result",
        json={"stdout": '{"cpu": 12.5, "disk": 45.0}', "exit_code": 0},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "COMPLETED"

    db_session.expire_all()
    task = db_session.get(Task, task_id)
    assert task.status == "COMPLETED"
    assert task.result == '{"cpu": 12.5, "disk": 45.0}'


# ── Full blueprint task flow ──────────────────────────────────────────────────

def test_full_blueprint_task_flow(client, db_session):
    """Same as script flow but workload_type=blueprint → heartbeat returns blueprint_url."""
    from orchestrator.models import Task

    node_id = f"aether-{uuid.uuid4().hex[:32]}"
    client.post("/api/v1/nodes/register", json=_register_payload(node_id))

    task_id = str(uuid.uuid4())
    db_session.add(Task(
        id=task_id, node_id=node_id,
        script_name="tpp_logistics.yml",
        status="PENDING", workload_type="blueprint",
    ))
    db_session.commit()

    resp = client.post("/api/v1/nodes/heartbeat", json={"node_id": node_id})
    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "EXECUTE"
    assert data["task_id"] == task_id
    assert data["workload_type"] == "blueprint"
    assert "tpp_logistics.yml" in data["blueprint_url"]
    assert not data.get("script_url")

    resp = client.post(
        f"/api/v1/tasks/{task_id}/result",
        json={"stdout": "Blueprint ran successfully.", "exit_code": 0},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "COMPLETED"


# ── Result submission edge cases ──────────────────────────────────────────────

def test_result_submission_404_on_unknown_task(client):
    resp = client.post(
        f"/api/v1/tasks/{uuid.uuid4()}/result",
        json={"stdout": "output", "exit_code": 0},
    )
    assert resp.status_code == 404


def test_result_submission_409_if_not_running(client, db_session):
    """Submitting a result for a PENDING (not yet dispatched) task should return 409."""
    from orchestrator.models import Task

    node_id = f"aether-{uuid.uuid4().hex[:32]}"
    client.post("/api/v1/nodes/register", json=_register_payload(node_id))

    task_id = str(uuid.uuid4())
    db_session.add(Task(
        id=task_id, node_id=node_id,
        script_name="test.py", status="PENDING", workload_type="script",
    ))
    db_session.commit()

    resp = client.post(
        f"/api/v1/tasks/{task_id}/result",
        json={"stdout": "too early", "exit_code": 0},
    )
    assert resp.status_code == 409


# ── Blueprint YAML validation ─────────────────────────────────────────────────

def test_blueprint_yaml_validation_valid():
    from aetheredge.runner import BlueprintRunner
    runner = BlueprintRunner("node-test", "https://localhost:8001", ("a", "b"), "ca.crt")
    with tempfile.NamedTemporaryFile(suffix=".yml", mode="w", delete=False) as f:
        f.write("services:\n  web:\n    image: nginx\n")
        tmp = Path(f.name)
    try:
        runner._validate(tmp)  # should not raise
    finally:
        tmp.unlink()


def test_blueprint_yaml_validation_rejects_invalid_yaml():
    from aetheredge.runner import BlueprintRunner
    runner = BlueprintRunner("node-test", "https://localhost:8001", ("a", "b"), "ca.crt")
    with tempfile.NamedTemporaryFile(suffix=".yml", mode="w", delete=False) as f:
        f.write(":\nbroken: [yaml\n")
        tmp = Path(f.name)
    try:
        with pytest.raises(ValueError, match="not valid YAML"):
            runner._validate(tmp)
    finally:
        tmp.unlink()


def test_blueprint_yaml_validation_rejects_missing_services():
    from aetheredge.runner import BlueprintRunner
    runner = BlueprintRunner("node-test", "https://localhost:8001", ("a", "b"), "ca.crt")
    with tempfile.NamedTemporaryFile(suffix=".yml", mode="w", delete=False) as f:
        f.write("name: not-a-compose-file\nfoo: bar\n")
        tmp = Path(f.name)
    try:
        with pytest.raises(ValueError, match="services"):
            runner._validate(tmp)
    finally:
        tmp.unlink()


# ── CrewAI agent subprocess ───────────────────────────────────────────────────

def test_crew_logistics_agent_runs_and_returns_json():
    """Run crew_logistics_agent.py as subprocess and verify JSON output."""
    agent_path = (
        Path(__file__).resolve().parents[1]
        / "orchestrator" / "registry" / "crew_logistics_agent.py"
    )
    result = subprocess.run(
        [sys.executable, str(agent_path)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"Agent failed:\n{result.stderr}"

    stdout = result.stdout
    start = stdout.find("{")
    end = stdout.rfind("}") + 1
    assert start != -1, "No JSON found in agent output"
    report = json.loads(stdout[start:end])

    assert "summary" in report
    assert "recommendation" in report
    assert "delayed_shipments" in report
    assert report["summary"]["total_shipments"] == 4
    assert report["summary"]["severity"] in ("LOW", "MEDIUM", "HIGH")
