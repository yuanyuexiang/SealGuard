from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

from app.domain.detection.entities import Detection, DetectionResult

# Prevent ultralytics from auto-installing dependencies at runtime.
os.environ.setdefault("YOLO_AUTOINSTALL", "false")


class SealVisionEngine:
    def __init__(
        self,
        bundle_dir: Path,
        default_imgsz: int = 960,
        default_conf: float = 0.25,
        default_device: str = "cpu",
    ) -> None:
        self.bundle_dir = bundle_dir
        self.weights_path = bundle_dir / "model" / "sealvision_best.pt"
        self.classes_path = bundle_dir / "docs" / "classes.yaml"
        self.default_imgsz = default_imgsz
        self.default_conf = default_conf
        self.default_device = default_device

        self.class_map = self._load_class_map()
        self.model = self._load_model()

    def _load_class_map(self) -> dict[int, str]:
        if not self.classes_path.exists():
            return {0: "signature", 1: "stamp"}

        with self.classes_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        names = data.get("names", {})
        class_map: dict[int, str] = {}

        if isinstance(names, list):
            for idx, name in enumerate(names):
                class_map[idx] = str(name)
        elif isinstance(names, dict):
            for idx_str, name in names.items():
                class_map[int(idx_str)] = str(name)

        return class_map or {0: "signature", 1: "stamp"}

    def _load_model(self) -> Any:
        if not self.weights_path.exists():
            raise RuntimeError(f"Weights file not found: {self.weights_path}")

        try:
            from ultralytics import YOLO
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "Ultralytics is not installed. Please install API requirements first."
            ) from exc

        return YOLO(str(self.weights_path))

    def detect(
        self,
        file_name: str,
        image_bytes: bytes,
        imgsz: int | None = None,
        conf: float | None = None,
        device: str | None = None,
    ) -> DetectionResult:
        suffix = Path(file_name).suffix or ".jpg"

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(image_bytes)
            tmp_path = Path(tmp.name)

        try:
            results = self.model.predict(
                source=str(tmp_path),
                imgsz=imgsz or self.default_imgsz,
                conf=conf if conf is not None else self.default_conf,
                device=device or self.default_device,
                verbose=False,
            )
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

        if not results:
            raise RuntimeError("Model returned no result.")

        first_result = results[0]
        image_height, image_width = first_result.orig_shape

        detections: list[Detection] = []
        boxes = getattr(first_result, "boxes", None)

        if boxes is not None:
            for idx, box in enumerate(boxes):
                cls_id = int(box.cls.item())
                conf_score = float(box.conf.item())
                x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].tolist()]
                detections.append(
                    Detection(
                        id=idx,
                        label=self.class_map.get(cls_id, str(cls_id)),
                        confidence=round(conf_score, 4),
                        bbox=(round(x1, 2), round(y1, 2), round(x2 - x1, 2), round(y2 - y1, 2)),
                    )
                )

        detections.sort(key=lambda d: d.confidence, reverse=True)

        return DetectionResult(
            file_name=file_name,
            image_width=image_width,
            image_height=image_height,
            model_name=self.weights_path.name,
            detections=detections,
        )
