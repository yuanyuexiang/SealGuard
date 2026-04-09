from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from bootstrap.config import get_settings
from infrastructure.db.models import Base
from infrastructure.db.session import engine
from interfaces.api.routes import router as api_router

app = FastAPI(title="SealGuard API", version="0.1.0")
app.include_router(api_router)

settings = get_settings()
runtime_dir = Path(settings.runtime_dir)
runtime_dir.mkdir(parents=True, exist_ok=True)


@app.on_event("startup")
def startup_init() -> None:
    # Initialize runtime folders and DB tables for MVP mode.
    (runtime_dir / "uploads" / "orders").mkdir(parents=True, exist_ok=True)
    (runtime_dir / "uploads" / "templates").mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    # Simple schema patch for existing databases without migrations.
    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE templates ADD COLUMN IF NOT EXISTS embedding_json TEXT")
        )
        connection.execute(
            text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS customer_id INTEGER")
        )
        connection.execute(
            text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS audit_result VARCHAR(16)")
        )

        # Backfill/recompute final audit state for legacy tasks.
        connection.execute(
            text(
                """
                UPDATE tasks t
                SET status = 'pending_review', audit_result = NULL
                WHERE EXISTS (
                    SELECT 1
                    FROM detections d
                    WHERE d.task_id = t.task_id
                      AND d.result = 'suspicious'
                )
                """
            )
        )
        connection.execute(
            text(
                """
                UPDATE tasks t
                SET status = 'done', audit_result = 'false'
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM detections d
                    WHERE d.task_id = t.task_id
                      AND d.result = 'suspicious'
                )
                  AND EXISTS (
                    SELECT 1
                    FROM detections d
                    WHERE d.task_id = t.task_id
                      AND d.result = 'false'
                )
                """
            )
        )
        connection.execute(
            text(
                """
                UPDATE tasks t
                SET status = 'done', audit_result = 'true'
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM detections d
                    WHERE d.task_id = t.task_id
                      AND d.result = 'suspicious'
                )
                  AND NOT EXISTS (
                    SELECT 1
                    FROM detections d
                    WHERE d.task_id = t.task_id
                      AND d.result = 'false'
                )
                  AND EXISTS (
                    SELECT 1
                    FROM detections d
                    WHERE d.task_id = t.task_id
                      AND d.result = 'true'
                )
                """
            )
        )


app.mount(settings.static_url_prefix, StaticFiles(directory=settings.runtime_dir), name="static")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/db")
def health_db() -> dict[str, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok"}
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"database unavailable: {exc}") from exc


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "sealguard-api", "message": "running"}
