import logging
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from orchestrator.database import get_db
from orchestrator.models import Task
from orchestrator.mtls import require_unrevoked_cert
from orchestrator.schemas import (
    TaskCompleteRequest,
    TaskCreate,
    TaskResponse,
    TaskResultRequest,
    TaskResultResponse,
)

log = logging.getLogger("aether.orchestrator")

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


@router.post("/create", response_model=TaskResponse, status_code=201)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)):
    task = Task(
        task_id=str(uuid.uuid4()),
        type=payload.type,
        data=payload.data,
        status="pending",
        created_at=datetime.now(timezone.utc),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.post("/complete", response_model=TaskResponse)
def complete_task(
    payload: TaskCompleteRequest,
    db: Session = Depends(get_db),
    _cert: dict = Depends(require_unrevoked_cert),
):
    task = db.get(Task, payload.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.assigned_to != payload.node_id:
        raise HTTPException(status_code=403, detail="Task not assigned to this node")

    task.status = "complete"
    task.result = payload.result
    task.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(task)
    return task


@router.post("/{task_id}/result", response_model=TaskResultResponse)
def submit_result(
    task_id: str,
    payload: TaskResultRequest,
    db: Session = Depends(get_db),
    _cert: dict = Depends(require_unrevoked_cert),
):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    if task.status != "RUNNING":
        raise HTTPException(
            status_code=409,
            detail=f"Task is '{task.status}', expected 'RUNNING'.",
        )

    task.result = payload.stdout
    task.status = "COMPLETED"
    task.updated_at = datetime.now(timezone.utc)
    db.commit()

    log.info(
        "Task completed — id=%s script=%s exit_code=%d output_bytes=%d",
        task.id,
        task.script_name,
        payload.exit_code,
        len(payload.stdout),
    )

    return TaskResultResponse(
        task_id=task.id,
        status="COMPLETED",
        message=f"Task '{task.script_name}' completed with exit code {payload.exit_code}.",
    )


@router.get("/", response_model=List[TaskResponse])
def list_tasks(db: Session = Depends(get_db)):
    return db.query(Task).order_by(Task.created_at.desc()).all()
