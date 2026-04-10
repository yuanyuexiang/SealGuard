from __future__ import annotations

from typing import Protocol

from app.domain.detection.entities import DetectionResult


class DetectionEnginePort(Protocol):
    def detect(
        self,
        file_name: str,
        image_bytes: bytes,
        imgsz: int | None = None,
        conf: float | None = None,
        device: str | None = None,
    ) -> DetectionResult: ...
