from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from application.detection.use_cases import DetectDeliveryNoteUseCase
from bootstrap.config import get_settings
from infrastructure.ai.sealvision_engine import SealVisionEngine


@lru_cache(maxsize=1)
def get_detection_engine() -> SealVisionEngine:
    settings = get_settings()
    return SealVisionEngine(
        bundle_dir=Path(settings.sealvision_bundle_dir),
        default_imgsz=settings.sealvision_img_size,
        default_conf=settings.sealvision_conf,
        default_device=settings.sealvision_device,
    )


@lru_cache(maxsize=1)
def get_detect_use_case() -> DetectDeliveryNoteUseCase:
    return DetectDeliveryNoteUseCase(engine=get_detection_engine())
