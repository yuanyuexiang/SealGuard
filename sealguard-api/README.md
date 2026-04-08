# sealguard-api

Backend API service for SealGuard.

## Stack
- FastAPI
- SQLAlchemy
- Pydantic

## Run (uvicorn)
```bash
uv sync --python 3.12
uvicorn main:app --reload
```

Production example:

```bash
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2
```

## DDD structure (no app directory)

```text
sealguard-api/
├─ main.py
├─ interfaces/      # FastAPI controllers and DTO
├─ application/     # Use cases (workflow orchestration)
├─ domain/          # Entities, value objects, ports
├─ infrastructure/  # DB/AI adapters and external implementations
├─ bootstrap/       # Config and dependency wiring
├─ shared/          # Shared utilities
├─ .env
├─ pyproject.toml
└─ uv.lock
```

## PostgreSQL backend config

The backend reads DB configuration from `.env` automatically.

Configured value example:

```env
DATABASE_URL=postgresql+psycopg2://postgres:123456@localhost:5432/sealguard
```

Modules:

- `bootstrap/config.py`: load and build database settings
- `infrastructure/db/session.py`: create SQLAlchemy engine and SessionLocal

## SealVision detection microservice

This API includes a migrated detection service from:

`sealguard-ai/sealvision_model_bundle_20260408`

Default expected model bundle path:

`../sealguard-ai/sealvision_model_bundle_20260408`

You can override with env vars:

```bash
export SEALVISION_BUNDLE_DIR=/absolute/path/to/sealvision_model_bundle_20260408
export SEALVISION_DEVICE=cpu
export SEALVISION_IMG_SIZE=960
export SEALVISION_CONF=0.25
```

### API

`POST /api/detect`

- Form field: `file` (image)
- Query params (optional):
	- `imgsz` (320~2048)
	- `conf` (0.01~0.99)
	- `device` (`cpu`/`mps`/`cuda`)

Example:

```bash
curl -X POST "http://127.0.0.1:8000/api/detect?imgsz=960&conf=0.25&device=cpu" \
	-F "file=@/path/to/delivery_note.jpg"
```
