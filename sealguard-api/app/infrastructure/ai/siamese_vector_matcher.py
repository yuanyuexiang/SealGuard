from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import cv2
import numpy as np

logger = logging.getLogger(__name__)


# --- Augmentation pipeline (deterministic, OpenCV-only) ----------------------

def _augment_variants(image: np.ndarray) -> list[np.ndarray]:
    """Produce a deterministic set of augmented variants of one crop.

    Aim: cover the realistic invariances of stamps/signatures without random
    seeds, so prototype/embedding payloads are reproducible across runs.
    """
    if image is None or image.size == 0:
        return []

    h, w = image.shape[:2]
    if h < 4 or w < 4:
        return [image]

    variants: list[np.ndarray] = [image]

    # Mild rotations to cover hand-held photo skew.
    for angle in (-7.0, -3.5, 3.5, 7.0):
        matrix = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), angle, 1.0)
        rotated = cv2.warpAffine(
            image, matrix, (w, h), borderMode=cv2.BORDER_REPLICATE
        )
        variants.append(rotated)

    # Brightness / contrast jitter to cover scanner exposure differences.
    variants.append(cv2.convertScaleAbs(image, alpha=1.1, beta=8))
    variants.append(cv2.convertScaleAbs(image, alpha=0.9, beta=-8))

    # Light blur to cover de-focus.
    variants.append(cv2.GaussianBlur(image, (3, 3), 0))

    return variants


# --- Lightweight fallback encoder -------------------------------------------

class _LightweightFallback:
    def __init__(self, embedding_size: tuple[int, int] = (32, 16)) -> None:
        self.embedding_size = embedding_size

    def encode_image(self, image_bytes: bytes) -> list[float]:
        image = _decode_image(image_bytes)
        return self._to_embedding(image)

    def encode_crop(self, image_bytes: bytes, bbox: Iterable[float]) -> list[float]:
        image = _crop_from_bbox(_decode_image(image_bytes), bbox)
        return self._to_embedding(image)

    def encode_image_variants(self, image_bytes: bytes) -> list[list[float]]:
        image = _decode_image(image_bytes)
        return [self._to_embedding(v) for v in _augment_variants(image)]

    def encode_crop_variants(
        self, image_bytes: bytes, bbox: Iterable[float]
    ) -> list[list[float]]:
        image = _crop_from_bbox(_decode_image(image_bytes), bbox)
        return [self._to_embedding(v) for v in _augment_variants(image)]

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


def _crop_from_bbox(image: np.ndarray, bbox: Iterable[float]) -> np.ndarray:
    h, w = image.shape[:2]
    x, y, bw, bh = [int(float(v)) for v in bbox]

    x1 = max(0, min(x, w - 1))
    y1 = max(0, min(y, h - 1))
    x2 = max(x1 + 1, min(x + bw, w))
    y2 = max(y1 + 1, min(y + bh, h))
    return image[y1:y2, x1:x2]


# --- Prototype payload -------------------------------------------------------

@dataclass(frozen=True)
class PrototypePayload:
    """Stored per-template payload for prototype-based matching.

    embeddings : K augmented embeddings (max-over-K matching at query time).
    prototype  : mean of `embeddings` (l2-normalised).
    intra_min  : min pairwise cosine within `embeddings` (encoder stability).
    intra_mean : mean pairwise cosine within `embeddings`.
    n_samples  : K.
    version    : payload schema version, future-proofing migrations.
    """

    embeddings: list[list[float]]
    prototype: list[float]
    intra_min: float
    intra_mean: float
    n_samples: int
    version: int = 1

    def to_dict(self) -> dict:
        return {
            "embeddings": self.embeddings,
            "prototype": self.prototype,
            "intra_min": self.intra_min,
            "intra_mean": self.intra_mean,
            "n_samples": self.n_samples,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PrototypePayload | None":
        if not isinstance(data, dict):
            return None
        embeddings = data.get("embeddings") or []
        prototype = data.get("prototype") or []
        if not embeddings or not prototype:
            return None
        return cls(
            embeddings=[list(map(float, e)) for e in embeddings],
            prototype=list(map(float, prototype)),
            intra_min=float(data.get("intra_min", 1.0)),
            intra_mean=float(data.get("intra_mean", 1.0)),
            n_samples=int(data.get("n_samples", len(embeddings))),
            version=int(data.get("version", 1)),
        )


def _l2_normalise(vector: Sequence[float]) -> np.ndarray:
    arr = np.asarray(list(vector), dtype=np.float32)
    norm = float(np.linalg.norm(arr))
    if norm <= 1e-8:
        return arr
    return arr / norm


def _cosine_to_unit(score: float) -> float:
    """Map raw cosine in [-1, 1] to [0, 1] (legacy convention used by routes)."""
    return max(0.0, min(1.0, (float(score) + 1.0) / 2.0))


_BACKEND_FALLBACK = "fallback"
_BACKEND_TORCH = "torch"
_BACKEND_ONNX = "onnx"

# ImageNet stats — used when the backend is an ONNX export of a standard
# vision backbone (DINOv2, ViT, ResNet, etc.). Most ONNX vision exports
# expect this normalisation.
_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


class SiameseVectorMatcher:
    """Siamese embedding matcher backed by real model weights.

    Supports four backends, picked at construction time from the file
    extension of `weights_path`:

    - ``.onnx``        → onnxruntime InferenceSession (e.g. DINOv2 export).
                          Inputs are normalised with ImageNet mean/std and the
                          first output is taken; if it is a token sequence
                          (``[B, T, D]``) we take the CLS index 0. Output is
                          L2-normalised.
    - ``.jit`` / ``.ts`` → ``torch.jit.load`` TorchScript model. The model is
                          expected to be self-contained (preprocessing baked
                          in via wrapping at export time).
    - other torch checkpoint → loaded into the internal small ``_EmbeddingNet``.
    - none of the above (or any failure when ``allow_lightweight_fallback``
      is set) → deterministic OpenCV pHash-style descriptor.
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
        self._onnx_session = None
        self._onnx_input_name = None
        self._backend: str = _BACKEND_FALLBACK

        self._load_model_or_fallback()

    @property
    def backend(self) -> str:
        return self._backend

    # --- Single embeddings (backward compatible) ---------------------------

    def encode_image(self, image_bytes: bytes) -> list[float]:
        return self._encode_one(_decode_image(image_bytes))

    def encode_crop(self, image_bytes: bytes, bbox: Iterable[float]) -> list[float]:
        crop = _crop_from_bbox(_decode_image(image_bytes), bbox)
        return self._encode_one(crop)

    # --- Augmented embeddings (new) ---------------------------------------

    def encode_image_variants(self, image_bytes: bytes) -> list[list[float]]:
        image = _decode_image(image_bytes)
        return [self._encode_one(v) for v in _augment_variants(image)]

    def encode_crop_variants(
        self, image_bytes: bytes, bbox: Iterable[float]
    ) -> list[list[float]]:
        crop = _crop_from_bbox(_decode_image(image_bytes), bbox)
        return [self._encode_one(v) for v in _augment_variants(crop)]

    # --- Backend dispatcher ------------------------------------------------

    def _encode_one(self, image: np.ndarray) -> list[float]:
        if self._backend == _BACKEND_TORCH:
            return self._encode_with_torch(image)
        if self._backend == _BACKEND_ONNX:
            return self._encode_with_onnx(image)
        return self._fallback._to_embedding(image)

    # --- Prototype building & matching ------------------------------------

    @staticmethod
    def build_prototype(embeddings: Sequence[Sequence[float]]) -> PrototypePayload | None:
        if not embeddings:
            return None
        normed = np.stack([_l2_normalise(e) for e in embeddings])
        prototype = normed.mean(axis=0)
        proto_norm = float(np.linalg.norm(prototype))
        if proto_norm > 1e-8:
            prototype = prototype / proto_norm

        # Pairwise cosine within the variant set (encoder stability proxy).
        if len(normed) > 1:
            sims = normed @ normed.T
            iu = np.triu_indices_from(sims, k=1)
            pairwise = sims[iu]
            intra_min = float(np.min(pairwise))
            intra_mean = float(np.mean(pairwise))
        else:
            intra_min = 1.0
            intra_mean = 1.0

        return PrototypePayload(
            embeddings=[
                [round(float(v), 6) for v in e.tolist()] for e in normed
            ],
            prototype=[round(float(v), 6) for v in prototype.tolist()],
            intra_min=round(intra_min, 6),
            intra_mean=round(intra_mean, 6),
            n_samples=len(normed),
            version=1,
        )

    def score_against_prototype(
        self,
        query_embedding: Sequence[float],
        payload: PrototypePayload,
    ) -> float:
        """Max-over-K cosine between query and stored augmented variants.

        Falls back to prototype-only cosine when variants are absent.
        Returned score is mapped to [0, 1] (same convention as the legacy
        `cosine_similarity` helper).
        """
        q = _l2_normalise(query_embedding)
        if payload.embeddings:
            variants = np.asarray(payload.embeddings, dtype=np.float32)
            sims = variants @ q
            best = float(np.max(sims))
        else:
            proto = _l2_normalise(payload.prototype)
            best = float(np.dot(proto, q))
        return _cosine_to_unit(best)

    @staticmethod
    def adaptive_thresholds(
        payload: PrototypePayload | None,
        *,
        base_high: float = 0.85,
        base_low: float = 0.6,
        max_relax: float = 0.08,
    ) -> tuple[float, float]:
        """Lower thresholds when the encoder is less stable on this template.

        If even the augmented variants of the SAME template only agree with
        intra_min ~0.7, asking the query to clear 0.85 is too strict — the
        encoder simply does not produce that level of similarity for genuine
        variations. Cap relaxation at `max_relax`.
        """
        if payload is None:
            return base_high, base_low
        instability = max(0.0, 1.0 - float(payload.intra_min))
        relax = min(max_relax, instability * 0.5)
        return max(0.5, base_high - relax), max(0.3, base_low - relax)

    # --- Cosine helper kept for backward compatibility --------------------

    def cosine_similarity(self, v1: Iterable[float], v2: Iterable[float]) -> float:
        a = np.asarray(list(v1), dtype=np.float32)
        b = np.asarray(list(v2), dtype=np.float32)

        denom = float(np.linalg.norm(a) * np.linalg.norm(b))
        if denom <= 1e-8:
            return 0.0
        score = float(np.dot(a, b) / denom)
        return _cosine_to_unit(score)

    # --- Internals --------------------------------------------------------

    def _load_model_or_fallback(self) -> None:
        try:
            if not self.weights_path.exists():
                raise FileNotFoundError(f"Siamese weights not found: {self.weights_path}")

            # 1) ONNX path — DINOv2 / ViT / ResNet etc. exported with `torch.onnx.export`.
            if self.weights_path.suffix == ".onnx":
                try:
                    import onnxruntime as ort  # type: ignore
                except Exception as exc:  # pragma: no cover - optional dep
                    raise RuntimeError(
                        "onnxruntime is not installed. "
                        "Install with: pip install onnxruntime"
                    ) from exc

                providers = ["CPUExecutionProvider"]
                if self.device.startswith("cuda"):
                    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]

                self._onnx_session = ort.InferenceSession(
                    str(self.weights_path), providers=providers
                )
                self._onnx_input_name = self._onnx_session.get_inputs()[0].name
                self._backend = _BACKEND_ONNX
                logger.info(
                    "Loaded Siamese ONNX model from %s (providers=%s, input=%s)",
                    self.weights_path,
                    providers,
                    self._onnx_input_name,
                )
                return

            # 2) Torch paths.
            import torch
            import torch.nn as nn

            self._torch = torch

            if self.weights_path.suffix in {".jit", ".ts"}:
                model = torch.jit.load(str(self.weights_path), map_location=self.device)
                model.eval()
                self._model = model
                self._backend = _BACKEND_TORCH
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
            self._backend = _BACKEND_TORCH
            logger.info("Loaded Siamese checkpoint model from %s", self.weights_path)
        except Exception as exc:
            if not self.allow_lightweight_fallback:
                raise RuntimeError(f"Failed to initialize Siamese model: {exc}") from exc

            logger.warning(
                "Siamese weights inference unavailable, falling back to deterministic embedding. reason=%s",
                exc,
            )
            self._backend = _BACKEND_FALLBACK

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
        if self._backend != _BACKEND_TORCH or self._torch is None or self._model is None:
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

    def _encode_with_onnx(self, image: np.ndarray) -> list[float]:
        if self._backend != _BACKEND_ONNX or self._onnx_session is None:
            raise RuntimeError("Siamese ONNX session is not initialized")

        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(
            rgb, (self.input_size, self.input_size), interpolation=cv2.INTER_AREA
        )
        arr = resized.astype(np.float32) / 255.0
        arr = (arr - _IMAGENET_MEAN) / _IMAGENET_STD
        # NCHW
        arr = np.transpose(arr, (2, 0, 1))[None, ...].astype(np.float32)

        outputs = self._onnx_session.run(None, {self._onnx_input_name: arr})
        out = outputs[0]

        # Accepted output shapes:
        #   [B, D]                  → take row 0 directly.
        #   [B, T, D] (token seq)   → take CLS at index 0.
        #   [D]                     → already squeezed.
        if out.ndim == 3:
            vec = out[0, 0, :]
        elif out.ndim == 2:
            vec = out[0]
        else:
            vec = np.asarray(out).reshape(-1)

        vec = vec.astype(np.float32)
        norm = float(np.linalg.norm(vec))
        if norm > 1e-8:
            vec = vec / norm
        return [round(float(v), 6) for v in vec.tolist()]
