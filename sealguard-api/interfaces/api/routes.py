from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from bootstrap.dependencies import get_detect_use_case
from domain.detection.entities import DetectionResult
from interfaces.api.dto.detect import DetectResponseDTO, DetectionItemDTO

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"message": "pong"}


def _to_response_dto(result: DetectionResult) -> DetectResponseDTO:
    return DetectResponseDTO(
        file_name=result.file_name,
        image_width=result.image_width,
        image_height=result.image_height,
        model_name=result.model_name,
        detections=[
            DetectionItemDTO(
                id=item.id,
                type=item.label,
                confidence=item.confidence,
                bbox=list(item.bbox),
            )
            for item in result.detections
        ],
    )


@router.post("/detect", response_model=DetectResponseDTO)
async def detect(
    file: UploadFile = File(...),
    imgsz: int | None = Query(default=None, ge=320, le=2048),
    conf: float | None = Query(default=None, ge=0.01, le=0.99),
    device: str | None = Query(default=None),
) -> DetectResponseDTO:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file must have a filename.")

    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files are supported.")

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        use_case = get_detect_use_case()
        result = use_case.execute(
            file_name=file.filename,
            image_bytes=image_bytes,
            imgsz=imgsz,
            conf=conf,
            device=device,
        )
        return _to_response_dto(result)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
