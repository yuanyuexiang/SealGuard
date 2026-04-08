from pydantic import BaseModel, Field


class DetectionItemDTO(BaseModel):
    id: int = Field(description="Detection index in current image")
    type: str = Field(description="Detected class label, e.g. signature/stamp")
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: list[float] = Field(
        min_length=4,
        max_length=4,
        description="[x, y, w, h] in pixel coordinates",
    )


class DetectResponseDTO(BaseModel):
    file_name: str
    image_width: int
    image_height: int
    model_name: str
    detections: list[DetectionItemDTO]
