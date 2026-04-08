# sealguard-api

Backend API service for SealGuard.

## Stack
- FastAPI
- SQLAlchemy
- Pydantic

## Run (uvicorn)
```bash
uv sync --python 3.12
uv run uvicorn main:app --reload
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
├─ artifacts/       # bundled model artifacts for detection
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

## File storage (no MinIO)

This version uses local file storage by default.

- Runtime directory: `./runtime`
- Static URL prefix: `/static`
- Uploaded order images: `./runtime/uploads/orders`
- Uploaded template images: `./runtime/uploads/templates`

Optional env vars:

```bash
export RUNTIME_DIR=/absolute/path/to/runtime
export STATIC_URL_PREFIX=/static
```

## SealVision detection microservice

This API includes a migrated detection service from:

`artifacts/sealvision`

Default expected model bundle path:

`./artifacts/sealvision`

Required files under bundle directory:

```text
model/sealvision_best.pt
docs/classes.yaml
```

You can override with env vars:

```bash
export SEALVISION_BUNDLE_DIR=/absolute/path/to/sealvision_model_bundle_20260408
export SEALVISION_DEVICE=cpu
export SEALVISION_IMG_SIZE=960
export SEALVISION_CONF=0.25
```

### API

Core admin APIs aligned with `sealguard-admin`:

- `GET /api/customers`
- `POST /api/customers`
- `GET /api/templates?customer_id={id}`
- `POST /api/templates/upload`
- `DELETE /api/templates/{template_id}`
- `POST /api/upload`
- `GET /api/result/{task_id}`
- `GET /api/tasks/{task_id}`
- `GET /api/tasks/latest`
- `POST /api/review`
- `GET /api/history`

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
