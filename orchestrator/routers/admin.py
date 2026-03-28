import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from orchestrator.database import get_db
from orchestrator.models import BootstrapToken, Node, Task
from orchestrator.schemas import AdminTaskCreate, RevokeResponse, TokenIssueRequest, TokenIssueResponse

TOKEN_EXPIRY_MINUTES = 10

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

_ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY", "")


def require_admin(request: Request) -> None:
    """Allow only localhost callers or requests bearing the correct API key."""
    client_host = request.client.host if request.client else ""
    if client_host in ("127.0.0.1", "::1"):
        return  # localhost — unconditionally trusted

    if not _ADMIN_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="ADMIN_API_KEY is not set on the server; remote admin access is disabled.",
        )

    key = request.headers.get("X-Admin-API-Key", "")
    if key != _ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Admin-API-Key.")


@router.post("/revoke/{node_id}", response_model=RevokeResponse)
def revoke_node(node_id: str, db: Session = Depends(get_db)):
    """
    Revoke a node's certificate. Its next heartbeat will be rejected with 403.
    Takes effect immediately — no restart or cert reissue needed.
    """
    node = db.get(Node, node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found.")
    if node.is_revoked:
        return RevokeResponse(node_id=node_id, is_revoked=True, message="Already revoked.")
    node.is_revoked = True
    db.commit()
    return RevokeResponse(node_id=node_id, is_revoked=True, message="Node revoked. Next heartbeat will be rejected.")


@router.post("/unrevoke/{node_id}", response_model=RevokeResponse)
def unrevoke_node(node_id: str, db: Session = Depends(get_db)):
    """Re-admit a previously revoked node."""
    node = db.get(Node, node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found.")
    node.is_revoked = False
    db.commit()
    return RevokeResponse(node_id=node_id, is_revoked=False, message="Node reinstated.")


@router.post("/tokens", response_model=TokenIssueResponse, status_code=201, dependencies=[Depends(require_admin)])
def issue_bootstrap_token(payload: TokenIssueRequest, db: Session = Depends(get_db)):
    """
    Issue a one-time bootstrap token bound to a device's MAC address.
    Expires in 10 minutes.  Can be called before the node boots (ZTP pre-provisioning).
    Pass the returned token to the device as AETHER_BOOTSTRAP_TOKEN env var.
    """
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=TOKEN_EXPIRY_MINUTES)

    # Invalidate any existing unused tokens for the same MAC so the admin
    # can re-issue without confusion if the window lapses.
    db.query(BootstrapToken).filter(
        BootstrapToken.mac_address == payload.mac_address,
        BootstrapToken.used == False,  # noqa: E712
    ).delete()

    token = secrets.token_urlsafe(32)
    record = BootstrapToken(
        token=token,
        mac_address=payload.mac_address,
        created_at=now,
        expires_at=expires_at,
        used=False,
    )
    db.add(record)
    db.commit()

    return TokenIssueResponse(
        token=token,
        mac_address=payload.mac_address,
        expires_at=expires_at,
    )


@router.post("/tasks", status_code=201, dependencies=[Depends(require_admin)])
def create_task_admin(payload: AdminTaskCreate, db: Session = Depends(get_db)):
    """Create a PENDING task for a specific node. Requires localhost or X-Admin-API-Key."""
    node = db.get(Node, payload.node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"Node '{payload.node_id}' not found.")

    task = Task(
        id=str(uuid.uuid4()),
        node_id=payload.node_id,
        script_name=payload.script_name,
        status="PENDING",
        workload_type=payload.workload_type,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    return {
        "task_id": task.id,
        "node_id": task.node_id,
        "script_name": task.script_name,
        "status": task.status,
        "created_at": task.created_at,
    }


@router.get("/nodes", tags=["admin"])
def list_nodes_admin(db: Session = Depends(get_db)):
    """List all nodes with revocation status."""
    nodes = db.query(Node).order_by(Node.registered_at.desc()).all()
    return [
        {
            "node_id": n.node_id,
            "hostname": n.hostname,
            "status": n.status,
            "is_revoked": bool(n.is_revoked),
            "last_seen_at": str(n.last_seen_at)[:19],
        }
        for n in nodes
    ]
