# sealguard-api

Backend API service for SealGuard.

## Stack
- FastAPI
- SQLAlchemy
- Pydantic

## Run (uvicorn)
```bash
uv sync --python 3.12
uv run uvicorn app.main:app --reload
```

Production example:

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
```

## DDD structure (with app directory)

```text
sealguard-api/
├─ app/
│  ├─ main.py
│  ├─ interfaces/      # FastAPI controllers and DTO
│  ├─ application/     # Use cases (workflow orchestration)
│  ├─ domain/          # Entities, value objects, ports
│  ├─ infrastructure/  # DB/AI adapters and external implementations
│  ├─ bootstrap/       # Config and dependency wiring
│  └─ shared/          # Shared utilities
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

- `app/bootstrap/config.py`: load and build database settings
- `app/infrastructure/db/session.py`: create SQLAlchemy engine and SessionLocal

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

## Siamese embedding matcher

The matcher now loads real Siamese weights for embedding inference.

Supported model formats:

- TorchScript (`.jit`, `.ts`)
- PyTorch checkpoint/state_dict (`.pt`, `.pth`)

Environment variables:

```bash
export SIAMESE_WEIGHTS_PATH=/absolute/path/to/siamese_best.pth
export SIAMESE_INPUT_SIZE=224
export SIAMESE_EMBEDDING_DIM=128
export SIAMESE_DEVICE=cpu
export SIAMESE_STRICT_LOADING=true
export SIAMESE_ALLOW_LIGHTWEIGHT_FALLBACK=true
```

If `SIAMESE_ALLOW_LIGHTWEIGHT_FALLBACK=false`, startup/request will fail when the Siamese
weights cannot be loaded.

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
- `POST /api/templates/rebuild-embeddings`

`POST /api/detect`

- Form field: `file` (image)
- Query params (optional):
	- `imgsz` (320~2048)
	- `conf` (0.01~0.99)
	- `device` (`cpu`/`mps`/`cuda`)

Example:

```bash
curl -X POST "http://127.0.0.1:8001/api/detect?imgsz=960&conf=0.25&device=cpu" \
	-F "file=@/path/to/delivery_note.jpg"
```

## Template embedding backfill

When historical templates have empty `embedding_json`, you can backfill in two ways:

Online API:

```bash
curl -X POST "http://127.0.0.1:8001/api/templates/rebuild-embeddings"
```

Offline script:

```bash
uv run python -m app.bootstrap.backfill_template_embeddings
```
