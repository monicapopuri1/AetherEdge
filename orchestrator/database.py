from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DB_PATH = Path.home() / ".aetheredge" / "orchestrator.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _connection_record):
    """
    Enable WAL mode for SQLite — dramatically improves write throughput under
    concurrent heartbeats (handles ~500 nodes before needing Postgres).
    NORMAL synchronous mode is safe for our use case and avoids fsync overhead.
    """
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_pending_task(node_id: str, db):
    from orchestrator.models import Task
    return (
        db.query(Task)
        .filter(Task.node_id == node_id, Task.status == "PENDING")
        .order_by(Task.created_at)
        .first()
    )
