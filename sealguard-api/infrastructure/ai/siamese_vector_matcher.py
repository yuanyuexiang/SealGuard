from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class _LightweightFallback:
    def __init__(self, embedding_size: tuple[int, int] = (32, 16)) -> None:
        self.embedding_size = embedding_size

    def encode_image(self, image_bytes: bytes) -> list[float]:
        image = _decode_image(image_bytes)
        return self._to_embedding(image)

    def encode_crop(self, image_bytes: bytes, bbox: Iterable[float]) -> list[float]:
        image = _decode_image(image_bytes)
        h, w = image.shape[:2]
        x, y, bw, bh = [int(float(v)) for v in bbox]

        x1 = max(0, min(x, w - 1))
        y1 = max(0, min(y, h - 1))
        x2 = max(x1 + 1, min(x + bw, w))
        y2 = max(y1 + 1, min(y + bh, h))
        crop = image[y1:y2, x1:x2]

        return self._to_embedding(crop)

    def _to_embedding(self, image: np.ndarray) -> list[float]:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, self.embedding_size, interpolation=cv2.INTER_AREA)
        vector = small.astype(np.float32).reshape(-1)

        mean = float(np.mean(vector))
        std = float(np.std(vector))
        std = std if std > 1e-6 else 1.0
        normalized = (vector - mean) / std

        return [round(float(v), 6) for v in normalized]


def _decode_image(image_bytes: bytes) -> np.ndarray:
    array = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError("Failed to decode image bytes")
    return image


class SiameseVectorMatcher:
    """Siamese embedding matcher backed by real model weights.

    Supports loading either:
    - TorchScript model (`torch.jit.load`), or
    - checkpoint/state_dict into an internal embedding net.
    """

    def __init__(
        self,
        *,
        weights_path: str,
        input_size: int = 224,
        embedding_dim: int = 128,
        device: str = "cpu",
        strict_loading: bool = True,
        allow_lightweight_fallback: bool = False,
    ) -> None:
        self.input_size = input_size
        self.embedding_dim = embedding_dim
        self.device = device
        self.strict_loading = strict_loading
        self.weights_path = Path(weights_path).expanduser()
        self.allow_lightweight_fallback = allow_lightweight_fallback

        self._fallback = _LightweightFallback()
        self._torch = None
        self._model = None
        self._is_torch_ready = False

        self._load_model_or_fallback()

    def encode_image(self, image_bytes: bytes) -> list[float]:
        if not self._is_torch_ready:
            return self._fallback.encode_image(image_bytes)
        image = _decode_image(image_bytes)
        return self._encode_with_torch(image)

    def encode_crop(self, image_bytes: bytes, bbox: Iterable[float]) -> list[float]:
        if not self._is_torch_ready:
            return self._fallback.encode_crop(image_bytes, bbox)

        image = _decode_image(image_bytes)
        h, w = image.shape[:2]
        x, y, bw, bh = [int(float(v)) for v in bbox]

        x1 = max(0, min(x, w - 1))
        y1 = max(0, min(y, h - 1))
        x2 = max(x1 + 1, min(x + bw, w))
        y2 = max(y1 + 1, min(y + bh, h))
        crop = image[y1:y2, x1:x2]

        return self._encode_with_torch(crop)

    def cosine_similarity(self, v1: Iterable[float], v2: Iterable[float]) -> float:
        a = np.asarray(list(v1), dtype=np.float32)
        b = np.asarray(list(v2), dtype=np.float32)

        denom = float(np.linalg.norm(a) * np.linalg.norm(b))
        if denom <= 1e-8:
            return 0.0
        score = float(np.dot(a, b) / denom)
        return max(0.0, min(1.0, (score + 1.0) / 2.0))

    def _load_model_or_fallback(self) -> None:
        try:
            import torch
            import torch.nn as nn

            self._torch = torch

            if not self.weights_path.exists():
                raise FileNotFoundError(f"Siamese weights not found: {self.weights_path}")

            if self.weights_path.suffix in {".jit", ".ts"}:
                model = torch.jit.load(str(self.weights_path), map_location=self.device)
                model.eval()
                self._model = model
                self._is_torch_ready = True
                logger.info("Loaded Siamese TorchScript model from %s", self.weights_path)
                return

            class _EmbeddingNet(nn.Module):
                def __init__(self, dim: int) -> None:
                    super().__init__()
                    self.backbone = nn.Sequential(
                        nn.Conv2d(3, 32, kernel_size=3, stride=2, padding=1),
                        nn.BatchNorm2d(32),
                        nn.ReLU(inplace=True),
                        nn.Conv2d(32, 64, kernel_size=3, stride=2, padding=1),
                        nn.BatchNorm2d(64),
                        nn.ReLU(inplace=True),
                        nn.Conv2d(64, 128, kernel_size=3, stride=2, padding=1),
                        nn.BatchNorm2d(128),
                        nn.ReLU(inplace=True),
                        nn.AdaptiveAvgPool2d((1, 1)),
                    )
                    self.proj = nn.Linear(128, dim)

                def forward(self, x):
                    x = self.backbone(x)
                    x = x.view(x.shape[0], -1)
                    x = self.proj(x)
                    return nn.functional.normalize(x, dim=1)

            checkpoint = torch.load(str(self.weights_path), map_location=self.device)
            state_dict = self._extract_state_dict(checkpoint)

            model = _EmbeddingNet(self.embedding_dim)
            model.load_state_dict(state_dict, strict=self.strict_loading)
            model.to(self.device)
            model.eval()

            self._model = model
            self._is_torch_ready = True
            logger.info("Loaded Siamese checkpoint model from %s", self.weights_path)
        except Exception as exc:
            if not self.allow_lightweight_fallback:
                raise RuntimeError(f"Failed to initialize Siamese model: {exc}") from exc

            logger.warning(
                "Siamese weights inference unavailable, falling back to deterministic embedding. reason=%s",
                exc,
            )
            self._is_torch_ready = False

    def _extract_state_dict(self, checkpoint: object) -> dict[str, object]:
        if isinstance(checkpoint, dict):
            for key in ("state_dict", "model_state_dict", "encoder_state_dict", "model", "encoder"):
                value = checkpoint.get(key)
                if isinstance(value, dict) and value:
                    return value

            # Some checkpoints store plain parameter mapping at root.
            if checkpoint and all(isinstance(k, str) for k in checkpoint.keys()):
                return checkpoint

        if hasattr(checkpoint, "state_dict"):
            return checkpoint.state_dict()

        raise RuntimeError("Unsupported Siamese checkpoint format")

    def _encode_with_torch(self, image: np.ndarray) -> list[float]:
        if not self._is_torch_ready or self._torch is None or self._model is None:
            raise RuntimeError("Siamese torch model is not initialized")

        torch = self._torch
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (self.input_size, self.input_size), interpolation=cv2.INTER_AREA)
        tensor = torch.from_numpy(resized).permute(2, 0, 1).contiguous().float() / 255.0
        tensor = tensor.unsqueeze(0).to(self.device)

        with torch.no_grad():
            embedding = self._model(tensor)

        if isinstance(embedding, (tuple, list)):
            embedding = embedding[0]

        vector = embedding.squeeze(0).detach().cpu().numpy().astype(np.float32)
        return [round(float(v), 6) for v in vector.tolist()]
