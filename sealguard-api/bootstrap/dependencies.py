from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Generator

from application.detection.use_cases import DetectDeliveryNoteUseCase
from bootstrap.config import get_settings
from infrastructure.ai.sealvision_engine import SealVisionEngine
from infrastructure.ai.siamese_vector_matcher import SiameseVectorMatcher
from infrastructure.db.session import SessionLocal
from infrastructure.storage.local_storage import LocalStorage


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


def get_db_session() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@lru_cache(maxsize=1)
def get_local_storage() -> LocalStorage:
    settings = get_settings()
    return LocalStorage(runtime_dir=Path(settings.runtime_dir), static_url_prefix=settings.static_url_prefix)


@lru_cache(maxsize=1)
def get_vector_matcher() -> SiameseVectorMatcher:
    settings = get_settings()
    return SiameseVectorMatcher(
        weights_path=settings.siamese_weights_path,
        input_size=settings.siamese_input_size,
        embedding_dim=settings.siamese_embedding_dim,
        device=settings.siamese_device,
        strict_loading=settings.siamese_strict_loading,
        allow_lightweight_fallback=settings.siamese_allow_lightweight_fallback,
    )
