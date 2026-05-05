"""Train a Siamese embedder on the SealGuard templates table.

Usage::

    pip install -r requirements.txt
    PYTHONPATH=../../sealguard-api python train.py \
        --database-url postgresql+psycopg2://postgres:123456@localhost:5432/sealguard \
        --runtime-dir ../../sealguard-api/runtime \
        --output ../../sealguard-api/artifacts/siamese/model/siamese_best.ts \
        --epochs 30 --batch-size 16

After training, point the API at the new weights::

    SIAMESE_WEIGHTS_PATH=./artifacts/siamese/model/siamese_best.ts
    SIAMESE_INPUT_SIZE=224
    SIAMESE_EMBEDDING_DIM=128
    SIAMESE_STRICT_LOADING=true
    # restart API, then trigger one-time prototype rebuild:
    curl -X POST 'http://localhost:8001/api/templates/rebuild-embeddings?force=true'

Why the API needs ``PYTHONPATH``: dataset.py reads from
``app.infrastructure.db.models`` to keep one source of truth for the schema.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader

# Allow running from any cwd: prepend repo's `sealguard-api` to PYTHONPATH so
# `from app.infrastructure.db.models import TemplateModel` resolves cleanly.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_API_ROOT = _REPO_ROOT / "sealguard-api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from dataset import TripletTemplateDataset, fetch_templates  # noqa: E402
from model import SiameseEmbedder, export_torchscript  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg2://postgres:123456@localhost:5432/sealguard",
        ),
    )
    parser.add_argument(
        "--runtime-dir",
        type=Path,
        default=Path(os.getenv("RUNTIME_DIR", str(_API_ROOT / "runtime"))),
        help="Same as the API's RUNTIME_DIR — used to resolve template image paths.",
    )
    parser.add_argument(
        "--static-url-prefix",
        default=os.getenv("STATIC_URL_PREFIX", "/static"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_API_ROOT / "artifacts" / "siamese" / "model" / "siamese_best.ts",
    )
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--epoch-size", type=int, default=4096)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--margin", type=float, default=0.2)
    parser.add_argument("--embedding-dim", type=int, default=128)
    parser.add_argument("--input-size", type=int, default=224)
    parser.add_argument("--num-workers", type=int, default=2)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--no-pretrained",
        action="store_true",
        help="Skip MobileNetV3-Small ImageNet weights. Almost always a bad idea.",
    )
    return parser.parse_args()


def train(args: argparse.Namespace) -> None:
    torch.manual_seed(args.seed)

    print(f"[1/4] fetching templates from {args.database_url}")
    rows = fetch_templates(args.database_url)
    print(f"      → {len(rows)} template rows")
    if len(rows) < 4:
        raise SystemExit(
            "Need at least 4 templates across at least 2 customers for triplet "
            "training to make sense. Upload more templates first."
        )

    dataset = TripletTemplateDataset(
        rows,
        runtime_dir=args.runtime_dir,
        static_url_prefix=args.static_url_prefix,
        input_size=args.input_size,
        epoch_size=args.epoch_size,
        augment=True,
        seed=args.seed,
    )
    loader = DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.num_workers,
        pin_memory=(args.device != "cpu"),
        drop_last=True,
    )

    print(f"[2/4] building MobileNetV3-Small embedder (dim={args.embedding_dim})")
    model = SiameseEmbedder(
        embedding_dim=args.embedding_dim,
        pretrained=not args.no_pretrained,
    ).to(args.device)

    optimiser = torch.optim.AdamW(
        model.parameters(), lr=args.lr, weight_decay=args.weight_decay
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimiser, T_max=args.epochs)
    triplet = nn.TripletMarginWithDistanceLoss(
        # We embed onto the unit hypersphere → 1 - cosine is the natural distance.
        distance_function=lambda a, b: 1.0 - (a * b).sum(dim=1),
        margin=args.margin,
    )

    print(f"[3/4] training for {args.epochs} epochs")
    best_loss = float("inf")
    args.output.parent.mkdir(parents=True, exist_ok=True)

    for epoch in range(1, args.epochs + 1):
        model.train()
        running, count, hard_mining = 0.0, 0, 0
        for a_imgs, p_imgs, n_imgs in loader:
            a_imgs = a_imgs.to(args.device, non_blocking=True)
            p_imgs = p_imgs.to(args.device, non_blocking=True)
            n_imgs = n_imgs.to(args.device, non_blocking=True)

            a = model(a_imgs)
            p = model(p_imgs)
            n = model(n_imgs)

            loss = triplet(a, p, n)
            optimiser.zero_grad()
            loss.backward()
            optimiser.step()

            running += float(loss.item()) * a.size(0)
            count += a.size(0)
            # Track hard triplets — those still violating the margin.
            with torch.no_grad():
                pos_d = 1.0 - (a * p).sum(dim=1)
                neg_d = 1.0 - (a * n).sum(dim=1)
                hard_mining += int((pos_d - neg_d + args.margin > 0).sum().item())

        scheduler.step()
        avg = running / max(1, count)
        ratio = hard_mining / max(1, count)
        print(
            f"  epoch {epoch:>3}/{args.epochs}  loss={avg:.4f}  "
            f"hard-triplet-ratio={ratio:.2%}  lr={scheduler.get_last_lr()[0]:.2e}"
        )

        if avg < best_loss:
            best_loss = avg
            print(f"      ↳ exporting TorchScript → {args.output}")
            export_torchscript(model.eval(), str(args.output), input_size=args.input_size)

    print(f"[4/4] done. best loss = {best_loss:.4f}")
    print(f"      weights at: {args.output}")
    print()
    print("Now run:")
    print(f"  export SIAMESE_WEIGHTS_PATH={args.output}")
    print(f"  export SIAMESE_EMBEDDING_DIM={args.embedding_dim}")
    print("  curl -X POST 'http://localhost:8001/api/templates/rebuild-embeddings?force=true'")


if __name__ == "__main__":
    train(parse_args())
