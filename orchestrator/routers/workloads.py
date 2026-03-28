import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

# Resolve workloads/ relative to the project root (two levels above this file)
WORKLOADS_DIR = Path(__file__).resolve().parents[2] / "workloads"

# Strict allowlist pattern — no path traversal, no arbitrary filenames
_SAFE_NAME = re.compile(r"^[a-zA-Z0-9_-]+\.py$")

router = APIRouter(prefix="/api/v1/workloads", tags=["workloads"])


@router.get("/{script_name}", response_class=PlainTextResponse)
def download_workload(script_name: str):
    """
    Serve a workload script to an authenticated node.
    Only filenames matching [a-zA-Z0-9_-]+.py are accepted — no path traversal.
    """
    if not _SAFE_NAME.match(script_name):
        raise HTTPException(status_code=400, detail="Invalid script name.")

    script_path = WORKLOADS_DIR / script_name
    if not script_path.exists():
        raise HTTPException(status_code=404, detail=f"Workload '{script_name}' not found.")

    return script_path.read_text()


@router.get("/", response_class=PlainTextResponse)
def list_workloads():
    """List available workload scripts."""
    if not WORKLOADS_DIR.exists():
        return "[]"
    scripts = [p.name for p in WORKLOADS_DIR.glob("*.py")]
    return "\n".join(sorted(scripts))
