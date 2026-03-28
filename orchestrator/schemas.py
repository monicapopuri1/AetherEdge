from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel


# ── Task schemas ──────────────────────────────────────────────────────────────

class TaskCreate(BaseModel):
    type: str
    data: Dict[str, Any]


class TaskResponse(BaseModel):
    task_id: str
    type: str
    data: Dict[str, Any]
    status: str
    assigned_to: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TaskCompleteRequest(BaseModel):
    task_id: str
    node_id: str
    result: Dict[str, Any]


class AdminTaskCreate(BaseModel):
    node_id: str
    script_name: str
    workload_type: str = "script"  # "script" | "blueprint"


class TaskResultRequest(BaseModel):
    stdout: str
    exit_code: int


class TaskResultResponse(BaseModel):
    task_id: str
    status: str
    message: str


# ── Heartbeat schemas ─────────────────────────────────────────────────────────

class HeartbeatRequest(BaseModel):
    node_id: str
    name: Optional[str] = None


class HeartbeatResponse(BaseModel):
    status: str
    task_id: Optional[str] = None
    action: Optional[str] = None         # "EXECUTE" when a task is dispatched
    workload_type: Optional[str] = None  # "script" | "blueprint"
    script_url: Optional[str] = None     # registry download URL (workload_type="script")
    blueprint_url: Optional[str] = None  # blueprint download URL (workload_type="blueprint")


# ── Auth / mTLS schemas ───────────────────────────────────────────────────────

class SignRequest(BaseModel):
    node_id: str
    csr_pem: str
    bootstrap_token: str  # One-time hardware-bound token from POST /api/v1/admin/tokens


class SignResponse(BaseModel):
    certificate_pem: str
    ca_cert_pem: str


# ── Bootstrap token schemas ────────────────────────────────────────────────────

class TokenIssueRequest(BaseModel):
    """Admin issues a token bound to a device MAC address before it boots."""
    mac_address: str


class TokenIssueResponse(BaseModel):
    token: str
    mac_address: str
    expires_at: datetime


# ── Node schemas ──────────────────────────────────────────────────────────────

class HardwareMetadata(BaseModel):
    hostname: str
    mac_address: str
    machine_id: str
    platform: str
    arch: str
    cpu_count: Optional[int] = None
    cpu_model: Optional[str] = None
    ram_total_gb: Optional[float] = None
    os_version: Optional[str] = None


class RegisterRequest(BaseModel):
    node_id: str
    public_key_pem: str
    hardware_metadata: HardwareMetadata
    timestamp_utc: str


class RegisterResponse(BaseModel):
    status: str
    node_id: str
    message: str
    registered_at: datetime
    last_seen_at: datetime


class NodeRecord(BaseModel):
    node_id: str
    name: Optional[str] = None
    hostname: str
    mac_address: str
    platform: str
    arch: str
    cpu_count: Optional[int] = None
    cpu_model: Optional[str] = None
    ram_total_gb: Optional[float] = None
    os_version: Optional[str] = None
    status: str
    is_revoked: bool = False
    registered_at: datetime
    last_seen_at: datetime

    model_config = {"from_attributes": True}


class RevokeResponse(BaseModel):
    node_id: str
    is_revoked: bool
    message: str
