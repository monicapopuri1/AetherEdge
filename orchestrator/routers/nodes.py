from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from orchestrator.database import get_db, get_pending_task
from orchestrator.models import Node, Task
from orchestrator.mtls import require_unrevoked_cert
from orchestrator.schemas import (
    HeartbeatRequest,
    HeartbeatResponse,
    NodeRecord,
    RegisterRequest,
    RegisterResponse,
)

router = APIRouter(prefix="/api/v1/nodes", tags=["nodes"])


@router.post("/register", response_model=RegisterResponse)
def register_node(payload: RegisterRequest, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    hw = payload.hardware_metadata

    existing = db.get(Node, payload.node_id)

    if existing:
        # Update last_seen and hardware in case it changed
        existing.last_seen_at = now
        existing.status = "ONLINE"
        existing.hostname = hw.hostname
        existing.mac_address = hw.mac_address
        existing.machine_id = hw.machine_id
        existing.platform = hw.platform
        existing.arch = hw.arch
        existing.cpu_count = hw.cpu_count
        existing.cpu_model = hw.cpu_model
        existing.ram_total_gb = hw.ram_total_gb
        existing.os_version = hw.os_version
        existing.public_key_pem = payload.public_key_pem
        db.commit()
        db.refresh(existing)
        node = existing
        message = "Node re-registered successfully."

        # Resilience: reset any RUNNING tasks back to PENDING so they get re-dispatched.
        # A RUNNING task at re-registration means the node crashed mid-execution.
        stuck = (
            db.query(Task)
            .filter(Task.node_id == payload.node_id, Task.status == "RUNNING")
            .all()
        )
        for t in stuck:
            t.status = "PENDING"
        if stuck:
            db.commit()
    else:
        node = Node(
            node_id=payload.node_id,
            public_key_pem=payload.public_key_pem,
            hostname=hw.hostname,
            mac_address=hw.mac_address,
            machine_id=hw.machine_id,
            platform=hw.platform,
            arch=hw.arch,
            cpu_count=hw.cpu_count,
            cpu_model=hw.cpu_model,
            ram_total_gb=hw.ram_total_gb,
            os_version=hw.os_version,
            registered_at=now,
            last_seen_at=now,
        )
        db.add(node)
        db.commit()
        db.refresh(node)
        message = "Node registered successfully."

    return RegisterResponse(
        status="registered",
        node_id=node.node_id,
        message=message,
        registered_at=node.registered_at,
        last_seen_at=node.last_seen_at,
    )


@router.post("/heartbeat", response_model=HeartbeatResponse)
def heartbeat(
    request: Request,
    payload: HeartbeatRequest,
    db: Session = Depends(get_db),
    _cert: dict = Depends(require_unrevoked_cert),
):
    node = db.get(Node, payload.node_id)
    if node:
        node.last_seen_at = datetime.now(timezone.utc)
        node.status = "ONLINE"
        if payload.name:
            node.name = payload.name
        db.commit()

    task = get_pending_task(payload.node_id, db)

    if task:
        task.status = "RUNNING"
        db.commit()

        base = str(request.base_url)
        workload_type = task.workload_type or "script"

        if workload_type == "blueprint":
            return HeartbeatResponse(
                status="ok",
                task_id=task.id,
                action="EXECUTE",
                workload_type="blueprint",
                blueprint_url=base + f"api/v1/blueprints/download/{task.script_name}",
            )

        return HeartbeatResponse(
            status="ok",
            task_id=task.id,
            action="EXECUTE",
            workload_type="script",
            script_url=base + f"api/v1/registry/download/{task.script_name}",
        )

    return HeartbeatResponse(status="ok")


@router.get("/", response_model=List[NodeRecord])
def list_nodes(db: Session = Depends(get_db)):
    return db.query(Node).order_by(Node.registered_at.desc()).all()
