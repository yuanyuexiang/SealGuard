from dataclasses import dataclass

from app.domain.detection.entities import DetectionResult
from app.domain.detection.ports import DetectionEnginePort


@dataclass
class DetectDeliveryNoteUseCase:
    engine: DetectionEnginePort

    def execute(
        self,
        *,
        file_name: str,
        image_bytes: bytes,
        imgsz: int | None = None,
        conf: float | None = None,
        device: str | None = None,
    ) -> DetectionResult:
        return self.engine.detect(
            file_name=file_name,
            image_bytes=image_bytes,
            imgsz=imgsz,
            conf=conf,
            device=device,
        )
