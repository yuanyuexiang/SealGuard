"""Siamese embedding model used for fine-tuning on the templates table.

The export target is a TorchScript file that the API loads via the ``.ts`` /
``.jit`` branch of ``SiameseVectorMatcher._load_model_or_fallback``. The
model takes ``[B, 3, H, W]`` floats in ``[0, 1]`` (NOT pre-normalised) and
emits ``[B, dim]`` L2-normalised embeddings, with ImageNet normalisation
baked in so the runtime needs zero special handling.
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F


_IMAGENET_MEAN = (0.485, 0.456, 0.406)
_IMAGENET_STD = (0.229, 0.224, 0.225)


class SiameseEmbedder(nn.Module):
    """ImageNet-pretrained MobileNetV3-Small + projection head.

    Why MobileNetV3-Small:
      - 2.5M params, ~60 MB in FP32, fast on CPU (the API runs on CPU by default).
      - Stronger than the toy 3-layer ConvNet that ``_EmbeddingNet`` defines,
        much cheaper than DINOv2-S (use the ONNX export flow for that).

    The projection head outputs ``embedding_dim`` floats and is L2-normalised
    so cosine similarity reduces to a dot product downstream.
    """

    def __init__(self, embedding_dim: int = 128, pretrained: bool = True) -> None:
        super().__init__()
        from torchvision.models import (
            MobileNet_V3_Small_Weights,
            mobilenet_v3_small,
        )

        weights = MobileNet_V3_Small_Weights.IMAGENET1K_V1 if pretrained else None
        backbone = mobilenet_v3_small(weights=weights)

        # Pull off the classifier; keep features + global pool, then add our head.
        self.features = backbone.features
        self.pool = nn.AdaptiveAvgPool2d(1)

        # MobileNetV3-Small's final feature dim is 576.
        self.proj = nn.Sequential(
            nn.Linear(576, 256),
            nn.Hardswish(),
            nn.Dropout(0.1),
            nn.Linear(256, embedding_dim),
        )

        # Bake ImageNet normalisation so the saved TorchScript is self-contained.
        self.register_buffer(
            "_mean",
            torch.tensor(_IMAGENET_MEAN, dtype=torch.float32).view(1, 3, 1, 1),
        )
        self.register_buffer(
            "_std",
            torch.tensor(_IMAGENET_STD, dtype=torch.float32).view(1, 3, 1, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x is in [0, 1].
        x = (x - self._mean) / self._std
        x = self.features(x)
        x = self.pool(x).flatten(1)
        x = self.proj(x)
        return F.normalize(x, dim=1)


def export_torchscript(model: SiameseEmbedder, output_path: str, input_size: int = 224) -> None:
    """Trace the model and write a TorchScript file the API can load directly."""
    model.eval()
    dummy = torch.zeros(1, 3, input_size, input_size, dtype=torch.float32)
    with torch.no_grad():
        traced = torch.jit.trace(model, dummy)
    traced.save(output_path)
