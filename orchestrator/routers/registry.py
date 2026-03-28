import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse

from orchestrator.mtls import require_unrevoked_cert

# Resolve registry/ relative to the project root (orchestrator/routers/ → orchestrator/ → registry/)
REGISTRY_DIR = Path(__file__).resolve().parents[1] / "registry"

# Strict allowlist — no path traversal, no arbitrary filenames
_SAFE_NAME = re.compile(r"^[a-zA-Z0-9_-]+\.py$")

router = APIRouter(prefix="/api/v1/registry", tags=["registry"])


@router.get("/download/{script_name}", response_class=PlainTextResponse)
def download_script(
    script_name: str,
    _cert: dict = Depends(require_unrevoked_cert),
):
    """
    Serve a registry script to an authenticated node.
    Requires a valid, unrevoked mTLS client certificate.
    Only filenames matching [a-zA-Z0-9_-]+.py are accepted — no path traversal.
    """
    if not _SAFE_NAME.match(script_name):
        raise HTTPException(status_code=400, detail="Invalid script name.")

    script_path = REGISTRY_DIR / script_name
    if not script_path.exists():
        raise HTTPException(status_code=404, detail=f"Script '{script_name}' not found.")

    return script_path.read_text()
