# sealguard-api

Backend API service for SealGuard.

## Stack
- FastAPI
- SQLAlchemy
- Pydantic

## Run
```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

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
