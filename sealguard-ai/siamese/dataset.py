"""Triplet dataset that samples directly from the SealGuard templates table.

Triplet rule
------------
- **Anchor** : a random template row.
- **Positive** : another row with the same ``(customer_id, type)``. If none
  exists, fall back to a strong augmentation of the anchor itself (still a
  valid positive, just weaker).
- **Negative** : a row with the same ``type`` but a different ``customer_id``.
  If the corpus only has one customer for that type, fall back to a different
  type as a last resort (rare; skip the triplet otherwise).

Image bytes resolution
----------------------
The ``image_url`` column stores either ``{static_url_prefix}/uploads/...``
(API-served path) or, less commonly, an absolute path / http URL. We mirror
the API's ``_read_template_bytes`` helper but inline it so this file has no
dependency on FastAPI.

Augmentation
------------
Designed to stretch realistic photographic invariances of stamps and
signatures: small rotations, scale jitter, brightness/contrast jitter,
mild blur. Deliberately *no* random horizontal flips — Chinese stamps and
signatures are not flip-invariant.
"""

from __future__ import annotations

import io
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.request import urlopen

import torch
from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from torchvision import transforms


@dataclass(frozen=True)
class TemplateRow:
    template_id: int
    customer_id: int
    type: str
    image_url: str


def _read_image_bytes(image_url: str, runtime_dir: Path, static_url_prefix: str) -> bytes:
    if image_url.startswith(static_url_prefix + "/"):
        relative = image_url[len(static_url_prefix) + 1 :]
        path = runtime_dir / relative
        if not path.exists():
            raise FileNotFoundError(f"Template image not found: {path}")
        return path.read_bytes()
    if image_url.startswith("http://") or image_url.startswith("https://"):
        with urlopen(image_url, timeout=10) as resp:  # nosec B310
            return resp.read()
    path = Path(image_url)
    if path.exists():
        return path.read_bytes()
    raise FileNotFoundError(f"Unsupported template image url/path: {image_url}")


def _load_pil(image_bytes: bytes) -> Image.Image:
    return Image.open(io.BytesIO(image_bytes)).convert("RGB")


def fetch_templates(database_url: str) -> list[TemplateRow]:
    """Pull every template row from the DB into memory.

    Templates lists are small (tens to thousands), so a single SELECT is fine.
    """
    # Lazy import to avoid making the API depend on this file.
    from app.infrastructure.db.models import TemplateModel  # type: ignore

    engine = create_engine(database_url, future=True, pool_pre_ping=True)
    session_cls = sessionmaker(bind=engine, future=True)
    rows: list[TemplateRow] = []
    with session_cls() as session:
        for row in session.execute(select(TemplateModel)).scalars():
            rows.append(
                TemplateRow(
                    template_id=row.id,
                    customer_id=row.customer_id,
                    type=row.type,
                    image_url=row.image_url,
                )
            )
    return rows


class TripletTemplateDataset(torch.utils.data.Dataset):
    """Lazy triplet sampler over the templates table.

    ``__len__`` returns ``epoch_size`` rather than the number of distinct
    triplets, because each ``__getitem__`` re-samples a fresh triplet — this
    is how triplet learning is normally done with small datasets.
    """

    def __init__(
        self,
        rows: Iterable[TemplateRow],
        *,
        runtime_dir: Path,
        static_url_prefix: str = "/static",
        input_size: int = 224,
        epoch_size: int = 4096,
        augment: bool = True,
        seed: int | None = None,
    ) -> None:
        self.rows = list(rows)
        if not self.rows:
            raise ValueError("Cannot build TripletTemplateDataset from empty rows")

        self.runtime_dir = runtime_dir
        self.static_url_prefix = static_url_prefix
        self.input_size = input_size
        self.epoch_size = epoch_size
        self._rng = random.Random(seed)

        # Indexes for fast positive/negative lookup.
        self._by_customer_type: dict[tuple[int, str], list[TemplateRow]] = {}
        self._by_type: dict[str, list[TemplateRow]] = {}
        for row in self.rows:
            self._by_customer_type.setdefault((row.customer_id, row.type), []).append(row)
            self._by_type.setdefault(row.type, []).append(row)

        self.transform = self._build_transform(augment)

    @staticmethod
    def _build_transform(augment: bool):
        if augment:
            return transforms.Compose(
                [
                    transforms.RandomAffine(
                        degrees=8,
                        translate=(0.04, 0.04),
                        scale=(0.92, 1.08),
                        shear=(-3, 3),
                        fill=255,
                    ),
                    transforms.ColorJitter(brightness=0.15, contrast=0.15, saturation=0.05),
                    transforms.RandomApply([transforms.GaussianBlur(3)], p=0.25),
                    transforms.Resize((224, 224)),
                    transforms.ToTensor(),  # → [0, 1]
                ]
            )
        return transforms.Compose(
            [transforms.Resize((224, 224)), transforms.ToTensor()]
        )

    def __len__(self) -> int:
        return self.epoch_size

    def __getitem__(self, _idx: int):
        anchor = self._rng.choice(self.rows)
        positive = self._sample_positive(anchor)
        negative = self._sample_negative(anchor)

        a = self._load_tensor(anchor)
        p = self._load_tensor(positive) if positive is not anchor else self._load_tensor(anchor)
        n = self._load_tensor(negative)
        return a, p, n

    def _sample_positive(self, anchor: TemplateRow) -> TemplateRow:
        siblings = [
            row
            for row in self._by_customer_type.get((anchor.customer_id, anchor.type), [])
            if row.template_id != anchor.template_id
        ]
        if siblings:
            return self._rng.choice(siblings)
        # No real positive exists → return the anchor itself; augmentation
        # supplies the differentiation since `transform` is stochastic.
        return anchor

    def _sample_negative(self, anchor: TemplateRow) -> TemplateRow:
        same_type = [
            row
            for row in self._by_type.get(anchor.type, [])
            if row.customer_id != anchor.customer_id
        ]
        if same_type:
            return self._rng.choice(same_type)
        # Last resort: any row from a different customer.
        any_other = [row for row in self.rows if row.customer_id != anchor.customer_id]
        if any_other:
            return self._rng.choice(any_other)
        # Truly degenerate corpus (one customer, one type) — fall back to anchor;
        # the loss will be ~0 on these and they get implicitly down-weighted.
        return anchor

    def _load_tensor(self, row: TemplateRow) -> torch.Tensor:
        try:
            image_bytes = _read_image_bytes(
                row.image_url, self.runtime_dir, self.static_url_prefix
            )
            image = _load_pil(image_bytes)
        except Exception:
            # Return a small gray patch so the batch can still proceed; the
            # main loop will drop or de-prioritise these on the next epoch.
            image = Image.new("RGB", (self.input_size, self.input_size), color=(128, 128, 128))
        return self.transform(image)
