from __future__ import annotations

from sqlalchemy import select

from infrastructure.db.models import CustomerModel, DetectionModel, ReviewModel, TaskModel, TemplateModel
from infrastructure.db.session import SessionLocal


def ensure_customer(session, name: str) -> CustomerModel:
    existing = session.execute(select(CustomerModel).where(CustomerModel.name == name)).scalar_one_or_none()
    if existing:
        return existing
    row = CustomerModel(name=name)
    session.add(row)
    session.flush()
    return row


def ensure_template(session, customer_id: int, template_type: str, image_url: str) -> TemplateModel:
    existing = (
        session.execute(
            select(TemplateModel).where(
                TemplateModel.customer_id == customer_id,
                TemplateModel.type == template_type,
                TemplateModel.image_url == image_url,
            )
        )
        .scalar_one_or_none()
    )
    if existing:
        return existing

    row = TemplateModel(customer_id=customer_id, type=template_type, image_url=image_url)
    session.add(row)
    session.flush()
    return row


def seed() -> None:
    with SessionLocal() as session:
        c1 = ensure_customer(session, "可口可乐华南配送中心")
        c2 = ensure_customer(session, "可口可乐华东供应链")

        t1 = ensure_template(
            session,
            customer_id=c1.id,
            template_type="signature",
            image_url="https://images.unsplash.com/photo-1545239351-1141bd82e8a6?q=80&w=1200&auto=format&fit=crop",
        )
        t2 = ensure_template(
            session,
            customer_id=c1.id,
            template_type="stamp",
            image_url="https://images.unsplash.com/photo-1455390582262-044cdead277a?q=80&w=1200&auto=format&fit=crop",
        )

        task = session.get(TaskModel, "task_demo_001")
        if task is None:
            task = TaskModel(
                task_id="task_demo_001",
                file_name="demo-delivery-note.jpg",
                image_url="/static/uploads/orders/demo-delivery-note.jpg",
                status="done",
            )
            session.add(task)
            session.flush()

            d1 = DetectionModel(
                task_id=task.task_id,
                type="signature",
                x=120.0,
                y=260.0,
                w=180.0,
                h=80.0,
                score=0.91,
                result="true",
                matched_template_url=t1.image_url,
            )
            d2 = DetectionModel(
                task_id=task.task_id,
                type="stamp",
                x=460.0,
                y=190.0,
                w=150.0,
                h=120.0,
                score=0.67,
                result="suspicious",
                matched_template_url=t2.image_url,
            )
            session.add_all([d1, d2])
            session.flush()

            review = ReviewModel(detect_id=d2.id, result="suspicious")
            session.add(review)

        session.commit()

        customer_count = session.query(CustomerModel).count()
        template_count = session.query(TemplateModel).count()
        task_count = session.query(TaskModel).count()
        detection_count = session.query(DetectionModel).count()
        review_count = session.query(ReviewModel).count()

        print("Seed completed")
        print(
            f"customers={customer_count}, templates={template_count}, "
            f"tasks={task_count}, detections={detection_count}, reviews={review_count}"
        )


if __name__ == "__main__":
    seed()
