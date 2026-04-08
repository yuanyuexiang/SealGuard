from dataclasses import dataclass


@dataclass(frozen=True)
class Detection:
    id: int
    label: str
    confidence: float
    bbox: tuple[float, float, float, float]


@dataclass(frozen=True)
class DetectionResult:
    file_name: str
    image_width: int
    image_height: int
    model_name: str
    detections: list[Detection]
