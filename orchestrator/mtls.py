"""
mTLS peer-certificate injection for FastAPI/uvicorn.

How it works:
  MTLSProtocol (H11Protocol subclass) overrides handle_events() to inject the
  TLS peer cert into the ASGI scope dict under the key "ssl_client_cert".
  FastAPI dependencies read it from request.scope["ssl_client_cert"].

  This scope-based approach works with uvicorn 0.30+, which removed handle().
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from orchestrator.database import get_db


def _get_node_id_from_cert(cert: dict) -> str | None:
    """Extract CN (node_id) from a peer cert dict returned by ssl.getpeercert()."""
    for rdn in cert.get("subject", []):
        for key, value in rdn:
            if key == "commonName":
                return value
    return None


def require_client_cert(request: Request) -> dict:
    """FastAPI dependency: rejects requests with no valid client certificate."""
    cert = request.scope.get("ssl_client_cert")
    if not cert:
        raise HTTPException(
            status_code=401,
            detail="mTLS client certificate required for this endpoint.",
        )
    return cert


def require_unrevoked_cert(
    cert: dict = Depends(require_client_cert),
    db: Session = Depends(get_db),
) -> dict:
    """
    FastAPI dependency: chains require_client_cert, then checks the node is not revoked.
    Extracts node_id from cert CN → DB lookup → 403 if is_revoked is True.
    """
    from orchestrator.models import Node  # local import avoids circular dependency

    node_id = _get_node_id_from_cert(cert)
    if node_id:
        node = db.get(Node, node_id)
        if node and node.is_revoked:
            raise HTTPException(
                status_code=403,
                detail=f"Certificate for node '{node_id}' has been revoked.",
            )
    return cert
