import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from orchestrator.database import get_db
from orchestrator.models import BootstrapToken, Node
from orchestrator.schemas import SignRequest, SignResponse
from orchestrator.security import SecurityManager, get_security_manager

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# Set AETHER_DISABLE_TOKEN_CHECK=1 during local development to skip token validation.
# Never set this in production.
_TOKEN_CHECK_DISABLED = os.environ.get("AETHER_DISABLE_TOKEN_CHECK", "").strip() == "1"


@router.post("/sign", response_model=SignResponse)
def sign_csr(
    payload: SignRequest,
    db: Session = Depends(get_db),
    security: SecurityManager = Depends(get_security_manager),
):
    """
    Bootstrap endpoint — no client cert required.
    Node must be registered via /api/v1/nodes/register first.
    Requires a valid one-time bootstrap token (from POST /api/v1/admin/tokens).
    Returns a CA-signed client cert + the CA cert for server verification.
    """
    if not _TOKEN_CHECK_DISABLED:
        _validate_bootstrap_token(payload.bootstrap_token, payload.node_id, db)

    node = db.get(Node, payload.node_id)
    if not node:
        raise HTTPException(
            status_code=404,
            detail=f"Node '{payload.node_id}' not found. Register first via /api/v1/nodes/register.",
        )

    try:
        cert_pem = security.sign_csr(payload.csr_pem, payload.node_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"CSR signing failed: {exc}")

    return SignResponse(
        certificate_pem=cert_pem,
        ca_cert_pem=security.get_ca_cert_pem(),
    )


def _validate_bootstrap_token(token: str, node_id: str, db: Session) -> None:
    """
    Validate a one-time bootstrap token:
      1. Token must exist and not be expired.
      2. Token must not have been used already (one-time guarantee).
      3. Token's MAC address must match the registering node's MAC address
         (hardware binding — prevents token theft across machines).
    Marks the token used on success so it cannot be replayed.
    """
    record = db.get(BootstrapToken, token)
    if not record:
        raise HTTPException(status_code=401, detail="Invalid bootstrap token.")

    now = datetime.now(timezone.utc)
    if record.expires_at.replace(tzinfo=timezone.utc) < now:
        raise HTTPException(status_code=410, detail="Bootstrap token has expired.")

    if record.used:
        raise HTTPException(status_code=409, detail="Bootstrap token has already been used.")

    # Hardware binding: look up the node and verify MAC matches the token
    node = db.get(Node, node_id)
    if not node:
        raise HTTPException(
            status_code=404,
            detail=f"Node '{node_id}' not found. Register first via /api/v1/nodes/register.",
        )
    if node.mac_address != record.mac_address:
        raise HTTPException(
            status_code=403,
            detail="Bootstrap token MAC address does not match this node's hardware.",
        )

    # Consume the token — one-time use
    record.used = True
    db.commit()
