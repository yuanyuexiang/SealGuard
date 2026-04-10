from __future__ import annotations

from sqlalchemy import select

from app.bootstrap.dependencies import get_vector_matcher
from app.bootstrap.seed_demo_data import seed
from app.infrastructure.db.models import TemplateModel
from app.infrastructure.db.session import SessionLocal
from app.interfaces.api.routes import _read_template_bytes


def run() -> None:
    # Ensure demo rows exist if user wants quick local verification.
    seed()

    matcher = get_vector_matcher()

    with SessionLocal() as session:
        rows = session.execute(select(TemplateModel).order_by(TemplateModel.id.asc())).scalars().all()
        total = len(rows)
        updated = 0
        skipped = 0

        for row in rows:
            if row.embedding_json:
                skipped += 1
                continue

            try:
                image_bytes = _read_template_bytes(row.image_url)
                embedding = matcher.encode_image(image_bytes)
                row.embedding_json = __import__("json").dumps(embedding, ensure_ascii=True)
                updated += 1
            except Exception:
                skipped += 1

        session.commit()

    print("Backfill completed")
    print(f"total={total}, updated={updated}, skipped={skipped}")


if __name__ == "__main__":
    run()
