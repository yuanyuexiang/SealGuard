from __future__ import annotations

import json

from sqlalchemy import select

from app.bootstrap.dependencies import get_vector_matcher
from app.bootstrap.seed_demo_data import seed
from app.infrastructure.db.models import TemplateModel
from app.infrastructure.db.session import SessionLocal
from app.interfaces.api.routes import _build_template_payload, _read_template_bytes


def run() -> None:
    """Build prototype payloads for any template that lacks one.

    Replaces the legacy single-embedding backfill: we now compute K augmented
    variants of each template image and store their prototype + max-over-K
    embedding set into `prototype_json`. The single `embedding_json` column
    is also kept up to date (prototype vector) so older readers do not break.
    """
    # Ensure demo rows exist if user wants quick local verification.
    seed()

    matcher = get_vector_matcher()

    with SessionLocal() as session:
        rows = session.execute(select(TemplateModel).order_by(TemplateModel.id.asc())).scalars().all()
        total = len(rows)
        updated = 0
        skipped = 0

        for row in rows:
            if row.prototype_json:
                skipped += 1
                continue

            try:
                image_bytes = _read_template_bytes(row.image_url)
                payload = _build_template_payload(matcher, image_bytes)
                if payload is None:
                    skipped += 1
                    continue
                row.prototype_json = json.dumps(payload.to_dict(), ensure_ascii=True)
                row.embedding_json = json.dumps(payload.prototype, ensure_ascii=True)
                updated += 1
            except Exception:
                skipped += 1

        session.commit()

    print("Backfill completed")
    print(f"total={total}, updated={updated}, skipped={skipped}")


if __name__ == "__main__":
    run()
