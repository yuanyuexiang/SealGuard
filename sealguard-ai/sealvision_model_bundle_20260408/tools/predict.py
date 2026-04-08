from __future__ import annotations

import argparse
import os
from pathlib import Path


# Prevent Ultralytics from attempting to pip-install optional deps (e.g. pi-heif)
os.environ.setdefault("YOLO_AUTOINSTALL", "false")


REPO_ROOT = Path(__file__).resolve().parents[1]


def resolve_from_repo(path_str: str) -> str:
    p = Path(path_str)
    return str(p if p.is_absolute() else (REPO_ROOT / p))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local inference for quick verification (non-service).")
    parser.add_argument("--weights", default="runs/detect/train/weights/best.pt", help="Path to .pt weights")
    parser.add_argument("--source", required=True, help="Image path, folder, video, or glob")
    parser.add_argument("--imgsz", type=int, default=960)
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument(
        "--device",
        default="cpu",
        help="Inference device: cpu/mps/cuda. Default cpu (matches Ubuntu CPU deployment).",
    )
    parser.add_argument("--project", default="runs/predict", help="Output project directory")
    parser.add_argument("--name", default="exp", help="Output run name")
    parser.add_argument("--save", action="store_true", help="Save rendered predictions")
    parser.add_argument("--save-txt", action="store_true", help="Save YOLO-format txt predictions")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    os.chdir(REPO_ROOT)

    from ultralytics import YOLO

    model = YOLO(resolve_from_repo(args.weights))

    results = model.predict(
        source=resolve_from_repo(args.source) if Path(args.source).exists() else args.source,
        imgsz=args.imgsz,
        conf=args.conf,
        device=args.device,
        save=args.save,
        save_txt=args.save_txt,
        project=resolve_from_repo(args.project),
        name=args.name,
    )

    # Ultralytics returns a list; the path is available on each result
    out_dir = None
    if results:
        out_dir = getattr(results[0], "save_dir", None)

    if out_dir:
        print(f"输出目录: {Path(out_dir)}")


if __name__ == "__main__":
    main()
