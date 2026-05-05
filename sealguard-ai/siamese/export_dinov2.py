"""Export a DINOv2-small ViT as an ONNX file the API can consume.

Usage::

    pip install torch torchvision onnx onnxruntime
    python export_dinov2.py --output ../sealguard-api/artifacts/siamese/model/siamese_best.onnx

What this produces
------------------
A self-contained ONNX file whose forward pass:

  1. takes a [B, 3, 224, 224] float32 tensor in [0, 1] (NOT pre-normalised);
  2. applies ImageNet mean/std internally;
  3. runs DINOv2-small (ViT-S/14, ~22M params, 384-dim CLS output);
  4. L2-normalises the output.

The matcher's ONNX backend already applies ImageNet normalisation in its
own preprocessing, so we deliberately *omit* the mean/std layer in the
exported graph here — keeping responsibilities single and avoiding double
normalisation. If you ever want a one-stop "feed raw uint8 → get embedding"
ONNX, set ``--bake-normalization`` and remove the matching step in
``_encode_with_onnx``.

Once exported, point the API at it::

    SIAMESE_WEIGHTS_PATH=./artifacts/siamese/model/siamese_best.onnx
    SIAMESE_INPUT_SIZE=224
    SIAMESE_EMBEDDING_DIM=384

Then trigger a one-time prototype rebuild::

    curl -X POST http://localhost:8001/api/templates/rebuild-embeddings?force=true
"""

from __future__ import annotations

import argparse
from pathlib import Path

import torch
import torch.nn as nn


_IMAGENET_MEAN = (0.485, 0.456, 0.406)
_IMAGENET_STD = (0.229, 0.224, 0.225)


class DinoV2EmbeddingWrapper(nn.Module):
    """Wraps a DINOv2 ViT to expose a fixed embedding API.

    Inputs : [B, 3, H, W] float in [0, 1]   (no normalisation expected)
    Outputs: [B, D]       L2-normalised CLS embedding
    """

    def __init__(self, backbone: nn.Module, *, bake_normalization: bool) -> None:
        super().__init__()
        self.backbone = backbone
        self.bake_normalization = bake_normalization
        if bake_normalization:
            self.register_buffer(
                "mean",
                torch.tensor(_IMAGENET_MEAN, dtype=torch.float32).view(1, 3, 1, 1),
            )
            self.register_buffer(
                "std",
                torch.tensor(_IMAGENET_STD, dtype=torch.float32).view(1, 3, 1, 1),
            )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if self.bake_normalization:
            x = (x - self.mean) / self.std
        # DINOv2 backbones expose `forward_features` returning a dict where
        # 'x_norm_clstoken' is the CLS embedding. They also support `.forward`
        # which returns the same CLS feature directly.
        if hasattr(self.backbone, "forward_features"):
            out = self.backbone.forward_features(x)
            if isinstance(out, dict):
                feat = out.get("x_norm_clstoken")
                if feat is None:
                    feat = out.get("x_norm_patchtokens")
                    feat = feat.mean(dim=1) if feat is not None else x.mean(dim=(2, 3))
            else:
                feat = out
        else:
            feat = self.backbone(x)
        return torch.nn.functional.normalize(feat, dim=1)


def load_dinov2(model_name: str = "dinov2_vits14") -> nn.Module:
    """Load a DINOv2 backbone via torch.hub. Requires internet on first call."""
    return torch.hub.load("facebookresearch/dinov2", model_name)


def export(
    *,
    output: Path,
    model_name: str,
    input_size: int,
    bake_normalization: bool,
    opset: int,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)

    print(f"[1/3] loading {model_name} via torch.hub …")
    backbone = load_dinov2(model_name)
    model = DinoV2EmbeddingWrapper(backbone, bake_normalization=bake_normalization).eval()

    print(f"[2/3] tracing forward with dummy input [1, 3, {input_size}, {input_size}] …")
    dummy = torch.zeros(1, 3, input_size, input_size, dtype=torch.float32)
    with torch.no_grad():
        out = model(dummy)
    print(f"      output shape: {tuple(out.shape)}, dtype: {out.dtype}")

    print(f"[3/3] exporting ONNX → {output}")
    torch.onnx.export(
        model,
        dummy,
        str(output),
        input_names=["image"],
        output_names=["embedding"],
        dynamic_axes={
            "image": {0: "batch"},
            "embedding": {0: "batch"},
        },
        opset_version=opset,
        do_constant_folding=True,
    )
    print("done.")
    print()
    print("Next steps:")
    print(f"  export SIAMESE_WEIGHTS_PATH={output}")
    print(f"  export SIAMESE_INPUT_SIZE={input_size}")
    print(f"  export SIAMESE_EMBEDDING_DIM={out.shape[-1]}")
    print("  curl -X POST http://localhost:8001/api/templates/rebuild-embeddings?force=true")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("./out/siamese_best.onnx"),
        help="Where to write the ONNX file.",
    )
    parser.add_argument(
        "--model-name",
        default="dinov2_vits14",
        choices=["dinov2_vits14", "dinov2_vitb14", "dinov2_vitl14"],
        help="DINOv2 variant. vits14 is the smallest and fastest on CPU.",
    )
    parser.add_argument(
        "--input-size",
        type=int,
        default=224,
        help="Square input edge in pixels. Must be a multiple of 14 for DINOv2.",
    )
    parser.add_argument(
        "--bake-normalization",
        action="store_true",
        help=(
            "Bake ImageNet mean/std into the ONNX graph. Only enable if you also "
            "modify the API to skip its own normalisation step."
        ),
    )
    parser.add_argument("--opset", type=int, default=17)
    args = parser.parse_args()

    if args.input_size % 14 != 0:
        raise SystemExit(
            f"--input-size must be divisible by 14 (DINOv2 patch size). "
            f"Got {args.input_size}."
        )

    export(
        output=args.output,
        model_name=args.model_name,
        input_size=args.input_size,
        bake_normalization=args.bake_normalization,
        opset=args.opset,
    )


if __name__ == "__main__":
    main()
