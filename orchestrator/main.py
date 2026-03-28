import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from sqlalchemy import text

from orchestrator.database import Base, SessionLocal, engine
from orchestrator.routers import admin, auth, blueprints, nodes, registry, tasks, workloads
from orchestrator.security import get_security_manager

log = logging.getLogger("aether.orchestrator")

STALE_THRESHOLD_SECONDS = 120  # 2 minutes
STALE_CHECK_INTERVAL = 30      # check every 30 seconds


def _run_migrations() -> None:
    """Add new columns to existing tables without Alembic."""
    with engine.connect() as conn:
        # ── tasks table: rebuild if it has the old schema (task_id primary key) ──
        columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(tasks)")).fetchall()
        }
        if columns and "id" not in columns:
            log.warning("Migration: tasks table has old schema — dropping and recreating.")
            conn.execute(text("DROP TABLE tasks"))
            conn.commit()
            Base.metadata.tables["tasks"].create(bind=engine)
            log.info("Migration: tasks table recreated with new schema.")

        # ── nodes table: add missing columns ─────────────────────────────────────
        new_columns = [
            "ALTER TABLE nodes ADD COLUMN status TEXT DEFAULT 'ONLINE'",
            "ALTER TABLE nodes ADD COLUMN cpu_count INTEGER",
            "ALTER TABLE nodes ADD COLUMN cpu_model TEXT",
            "ALTER TABLE nodes ADD COLUMN ram_total_gb REAL",
            "ALTER TABLE nodes ADD COLUMN os_version TEXT",
            "ALTER TABLE nodes ADD COLUMN is_revoked INTEGER DEFAULT 0",
            "ALTER TABLE nodes ADD COLUMN name TEXT",
            # ── tasks table: add missing columns ─────────────────────────────
            "ALTER TABLE tasks ADD COLUMN workload_type TEXT DEFAULT 'script'",
        ]
        for stmt in new_columns:
            try:
                conn.execute(text(stmt))
                conn.commit()
                col = stmt.split("ADD COLUMN")[1].strip().split()[0]
                log.info("Migration: added column '%s'.", col)
            except Exception as exc:
                # Expected when column already exists — log at debug level only
                col = stmt.split("ADD COLUMN")[1].strip().split()[0]
                log.debug("Migration: skipping column '%s' (already exists: %s).", col, exc)


async def _stale_node_checker() -> None:
    """Background task: mark nodes OFFLINE if silent for > 2 minutes."""
    while True:
        await asyncio.sleep(STALE_CHECK_INTERVAL)
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=STALE_THRESHOLD_SECONDS)
        db = SessionLocal()
        try:
            result = db.execute(
                text(
                    "UPDATE nodes SET status = 'OFFLINE' "
                    "WHERE status = 'ONLINE' AND last_seen_at < :cutoff"
                ),
                {"cutoff": cutoff.isoformat()},
            )
            db.commit()
            if result.rowcount:
                log.warning("Stale node check: marked %d node(s) OFFLINE.", result.rowcount)
        except Exception as exc:
            log.error("Stale node check failed: %s", exc)
        finally:
            db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    Base.metadata.create_all(bind=engine)
    _run_migrations()
    # Ensure CA exists so /api/v1/auth/sign works on first request
    get_security_manager().ensure_ca()
    checker = asyncio.create_task(_stale_node_checker())
    log.info("Stale node checker started (threshold=%ds).", STALE_THRESHOLD_SECONDS)
    yield
    # Shutdown
    checker.cancel()


app = FastAPI(
    title="AetherOrchestrator",
    description="Central registry for AetherEdge nodes",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(auth.router)
app.include_router(nodes.router)
app.include_router(tasks.router)
app.include_router(admin.router)
app.include_router(workloads.router)
app.include_router(registry.router)
app.include_router(blueprints.router)


@app.get("/health")
def health():
    return {"status": "ok"}
