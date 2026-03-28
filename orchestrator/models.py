from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from orchestrator.database import Base


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    node_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("nodes.node_id"), nullable=True, default=None
    )
    script_name: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="PENDING")
    # PENDING | RUNNING | COMPLETED | FAILED
    workload_type: Mapped[str] = mapped_column(String, default="script")
    # "script" — download .py and execute via subprocess
    # "blueprint" — download docker-compose.yaml and run via docker compose
    result: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Node(Base):
    __tablename__ = "nodes"

    node_id: Mapped[str] = mapped_column(String, primary_key=True)
    public_key_pem: Mapped[str] = mapped_column(Text)

    # Hardware metadata
    hostname: Mapped[str] = mapped_column(String)
    mac_address: Mapped[str] = mapped_column(String)
    machine_id: Mapped[str] = mapped_column(String)
    platform: Mapped[str] = mapped_column(String)
    arch: Mapped[str] = mapped_column(String)

    # System specs (collected live at registration)
    cpu_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=None)
    cpu_model: Mapped[Optional[str]] = mapped_column(String, nullable=True, default=None)
    ram_total_gb: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=None)
    os_version: Mapped[Optional[str]] = mapped_column(String, nullable=True, default=None)

    name: Mapped[Optional[str]] = mapped_column(String, nullable=True, default=None)

    status: Mapped[str] = mapped_column(String, default="ONLINE")  # ONLINE | OFFLINE
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False)

    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class BootstrapToken(Base):
    """
    One-time hardware-bound token for CSR signing.

    Flow:
      1. Admin calls POST /api/v1/admin/tokens with the node's MAC address
         (can be done before the node boots — zero-touch provisioning).
      2. Token is embedded in the bootstrap image as AETHER_BOOTSTRAP_TOKEN.
      3. On first boot the node registers, then POSTs the token with its CSR
         to /api/v1/auth/sign.
      4. The orchestrator validates expiry + MAC binding, signs the CSR, and
         marks the token used.  Subsequent calls with the same token are rejected.
    """
    __tablename__ = "bootstrap_tokens"

    token: Mapped[str] = mapped_column(String, primary_key=True)
    # MAC address of the device this token is bound to
    mac_address: Mapped[str] = mapped_column(String, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(Boolean, default=False)
