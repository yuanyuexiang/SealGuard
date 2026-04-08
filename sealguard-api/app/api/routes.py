from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from app.schemas.detect import DetectResponse
from app.services.sealvision_service import get_sealvision_service

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"message": "pong"}


@router.post("/detect", response_model=DetectResponse)
async def detect(
    file: UploadFile = File(...),
    imgsz: int | None = Query(default=None, ge=320, le=2048),
    conf: float | None = Query(default=None, ge=0.01, le=0.99),
    device: str | None = Query(default=None),
) -> DetectResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file must have a filename.")

    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files are supported.")

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        service = get_sealvision_service()
        return service.detect(
            file_name=file.filename,
            image_bytes=image_bytes,
            imgsz=imgsz,
            conf=conf,
            device=device,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
