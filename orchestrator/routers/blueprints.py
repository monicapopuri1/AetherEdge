import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse

from orchestrator.mtls import require_unrevoked_cert

# Resolve blueprints/ relative to the project root (orchestrator/routers/ → orchestrator/ → blueprints/)
BLUEPRINTS_DIR = Path(__file__).resolve().parents[1] / "blueprints"

# Allow only safe filenames: alphanumeric/underscore/hyphen with .yml or .yaml extension
_SAFE_NAME = re.compile(r"^[a-zA-Z0-9_-]+\.ya?ml$")

router = APIRouter(prefix="/api/v1/blueprints", tags=["blueprints"])


@router.get("/download/{blueprint_name}", response_class=PlainTextResponse)
def download_blueprint(
    blueprint_name: str,
    _cert: dict = Depends(require_unrevoked_cert),
):
    """
    Serve a Docker Compose blueprint to an authenticated node.
    Requires a valid, unrevoked mTLS client certificate.
    Only filenames matching [a-zA-Z0-9_-]+.yml|yaml are accepted — no path traversal.
    """
    if not _SAFE_NAME.match(blueprint_name):
        raise HTTPException(status_code=400, detail="Invalid blueprint name.")

    blueprint_path = BLUEPRINTS_DIR / blueprint_name
    if not blueprint_path.exists():
        raise HTTPException(status_code=404, detail=f"Blueprint '{blueprint_name}' not found.")

    return blueprint_path.read_text()


@router.get("/", response_class=PlainTextResponse)
def list_blueprints(_cert: dict = Depends(require_unrevoked_cert)):
    """List available blueprints."""
    if not BLUEPRINTS_DIR.exists():
        return ""
    files = sorted(p.name for p in BLUEPRINTS_DIR.glob("*.y*ml"))
    return "\n".join(files)
