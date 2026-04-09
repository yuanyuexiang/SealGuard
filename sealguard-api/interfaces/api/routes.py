from datetime import datetime
import json
from pathlib import Path
from urllib.request import urlopen
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bootstrap.config import get_settings
from bootstrap.dependencies import get_db_session, get_detect_use_case, get_local_storage, get_vector_matcher
from domain.detection.entities import DetectionResult
from infrastructure.ai.siamese_vector_matcher import SiameseVectorMatcher
from infrastructure.db.models import CustomerModel, DetectionModel, ReviewModel, TaskModel, TemplateModel
from infrastructure.storage.local_storage import LocalStorage
from interfaces.api.dto.business import (
    CustomerCreateRequest,
    CustomerDTO,
    CustomerStatsDTO,
    CustomerUpdateRequest,
    DetectionDTO,
    HistoryItemDTO,
    ReviewRecordDTO,
    ReviewRequest,
    TaskResultDTO,
    TemplateDTO,
    UploadOrderResponse,
    UploadTaskDTO,
)
from interfaces.api.dto.detect import DetectResponseDTO, DetectionItemDTO

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"message": "pong"}


def _to_iso(dt: datetime | None) -> str:
    if dt is None:
        return datetime.utcnow().isoformat()
    return dt.isoformat()


def _score_to_result(score: float) -> str:
    if score >= 0.85:
        return "true"
    if score >= 0.6:
        return "suspicious"
    return "false"


def _read_template_bytes(image_url: str) -> bytes:
    settings = get_settings()

    if image_url.startswith(settings.static_url_prefix + "/"):
        relative = image_url[len(settings.static_url_prefix) + 1 :]
        path = Path(settings.runtime_dir) / relative
        if not path.exists():
            raise RuntimeError(f"Template image not found: {path}")
        return path.read_bytes()

    if image_url.startswith("http://") or image_url.startswith("https://"):
        with urlopen(image_url, timeout=10) as resp:  # nosec B310
            return resp.read()

    path = Path(image_url)
    if path.exists():
        return path.read_bytes()

    raise RuntimeError(f"Unsupported template image url/path: {image_url}")


def _to_response_dto(result: DetectionResult) -> DetectResponseDTO:
    return DetectResponseDTO(
        file_name=result.file_name,
        image_width=result.image_width,
        image_height=result.image_height,
        model_name=result.model_name,
        detections=[
            DetectionItemDTO(
                id=item.id,
                type=item.label,
                confidence=item.confidence,
                bbox=list(item.bbox),
            )
            for item in result.detections
        ],
    )


def _to_detection_dto(row: DetectionModel) -> DetectionDTO:
    return DetectionDTO(
        id=row.id,
        task_id=row.task_id,
        type=row.type,
        bbox=[row.x, row.y, row.w, row.h],
        score=row.score,
        result=row.result,
        matched_template_url=row.matched_template_url,
    )


def _find_customer_by_name(db: Session, name: str, exclude_id: int | None = None) -> CustomerModel | None:
    stmt = select(CustomerModel).where(func.lower(CustomerModel.name) == name.lower())
    if exclude_id is not None:
        stmt = stmt.where(CustomerModel.id != exclude_id)
    return db.execute(stmt).scalars().first()


def _build_customer_stats(db: Session, customer_id: int) -> CustomerStatsDTO:
    customer = db.get(CustomerModel, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found.")

    template_rows = (
        db.execute(
            select(TemplateModel.type, func.count(TemplateModel.id))
            .where(TemplateModel.customer_id == customer_id)
            .group_by(TemplateModel.type)
        )
        .all()
    )

    signature_templates = 0
    stamp_templates = 0
    for row_type, row_count in template_rows:
        if row_type == "signature":
            signature_templates = int(row_count)
        elif row_type == "stamp":
            stamp_templates = int(row_count)

    return CustomerStatsDTO(
        customer_id=customer.id,
        customer_name=customer.name,
        template_total=signature_templates + stamp_templates,
        signature_templates=signature_templates,
        stamp_templates=stamp_templates,
    )


@router.get("/customers", response_model=list[CustomerDTO])
def get_customers(db: Session = Depends(get_db_session)) -> list[CustomerDTO]:
    rows = db.execute(select(CustomerModel).order_by(CustomerModel.id.desc())).scalars().all()

    count_rows = (
        db.execute(
            select(TemplateModel.customer_id, TemplateModel.type, func.count(TemplateModel.id))
            .group_by(TemplateModel.customer_id, TemplateModel.type)
        )
        .all()
    )
    count_map: dict[int, dict[str, int]] = {}
    for customer_id, template_type, template_count in count_rows:
        key = int(customer_id)
        if key not in count_map:
            count_map[key] = {"signature": 0, "stamp": 0}
        if template_type in {"signature", "stamp"}:
            count_map[key][template_type] = int(template_count)

    result: list[CustomerDTO] = []
    for row in rows:
        signature_templates = count_map.get(row.id, {}).get("signature", 0)
        stamp_templates = count_map.get(row.id, {}).get("stamp", 0)
        result.append(
            CustomerDTO(
                id=row.id,
                name=row.name,
                template_total=signature_templates + stamp_templates,
                signature_templates=signature_templates,
                stamp_templates=stamp_templates,
            )
        )

    return result


@router.post("/customers", response_model=CustomerDTO)
def create_customer(payload: CustomerCreateRequest, db: Session = Depends(get_db_session)) -> CustomerDTO:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Customer name cannot be empty.")

    duplicate = _find_customer_by_name(db, name)
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="Customer name already exists.")

    row = CustomerModel(name=name)
    db.add(row)
    db.commit()
    db.refresh(row)
    return CustomerDTO(id=row.id, name=row.name)


@router.put("/customers/{customer_id}", response_model=CustomerDTO)
def update_customer(
    customer_id: int,
    payload: CustomerUpdateRequest,
    db: Session = Depends(get_db_session),
) -> CustomerDTO:
    row = db.get(CustomerModel, customer_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Customer not found.")

    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Customer name cannot be empty.")

    duplicate = _find_customer_by_name(db, name, exclude_id=customer_id)
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="Customer name already exists.")

    row.name = name
    db.commit()
    db.refresh(row)
    return CustomerDTO(id=row.id, name=row.name)


@router.delete("/customers/{customer_id}")
def delete_customer(customer_id: int, db: Session = Depends(get_db_session)) -> dict[str, str]:
    row = db.get(CustomerModel, customer_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Customer not found.")

    db.delete(row)
    db.commit()
    return {"status": "ok"}


@router.get("/customers/{customer_id}/stats", response_model=CustomerStatsDTO)
def get_customer_stats(customer_id: int, db: Session = Depends(get_db_session)) -> CustomerStatsDTO:
    return _build_customer_stats(db, customer_id)


@router.get("/templates", response_model=list[TemplateDTO])
def get_templates(customer_id: int, db: Session = Depends(get_db_session)) -> list[TemplateDTO]:
    rows = (
        db.execute(
            select(TemplateModel)
            .where(TemplateModel.customer_id == customer_id)
            .order_by(TemplateModel.id.desc())
        )
        .scalars()
        .all()
    )
    return [
        TemplateDTO(
            id=row.id,
            customer_id=row.customer_id,
            type=row.type,
            image_url=row.image_url,
            created_at=_to_iso(row.created_at),
        )
        for row in rows
    ]


@router.post("/templates/upload", response_model=TemplateDTO)
async def upload_template(
    customer_id: int = Form(...),
    type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db_session),
    storage: LocalStorage = Depends(get_local_storage),
    matcher: SiameseVectorMatcher = Depends(get_vector_matcher),
) -> TemplateDTO:
    if type not in {"signature", "stamp"}:
        raise HTTPException(status_code=400, detail="Template type must be signature or stamp.")

    customer = db.get(CustomerModel, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found.")

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded template is empty.")

    embedding = matcher.encode_image(image_bytes)
    _, image_url = storage.save_image(image_bytes=image_bytes, original_name=file.filename or "template.jpg", category="templates")

    row = TemplateModel(
        customer_id=customer_id,
        type=type,
        image_url=image_url,
        embedding_json=json.dumps(embedding, ensure_ascii=True),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return TemplateDTO(
        id=row.id,
        customer_id=row.customer_id,
        type=row.type,
        image_url=row.image_url,
        created_at=_to_iso(row.created_at),
    )


@router.delete("/templates/{template_id}")
def delete_template(template_id: int, db: Session = Depends(get_db_session)) -> dict[str, str]:
    row = db.get(TemplateModel, template_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Template not found.")
    db.delete(row)
    db.commit()
    return {"status": "ok"}


@router.post("/upload", response_model=UploadOrderResponse)
async def upload_order(
    file: UploadFile = File(...),
    db: Session = Depends(get_db_session),
    storage: LocalStorage = Depends(get_local_storage),
    matcher: SiameseVectorMatcher = Depends(get_vector_matcher),
) -> UploadOrderResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file must have a filename.")

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    task_id = f"task_{uuid4().hex[:12]}"
    _, image_url = storage.save_image(image_bytes=image_bytes, original_name=file.filename, category="orders")

    task = TaskModel(task_id=task_id, file_name=file.filename, image_url=image_url, status="running")
    db.add(task)
    db.commit()

    try:
        use_case = get_detect_use_case()
        detect_result = use_case.execute(file_name=file.filename, image_bytes=image_bytes)

        for item in detect_result.detections:
            best_template: TemplateModel | None = None
            best_score = 0.0

            query_templates = (
                db.execute(
                    select(TemplateModel)
                    .where(
                        TemplateModel.type == item.label,
                        TemplateModel.embedding_json.is_not(None),
                    )
                    .order_by(TemplateModel.created_at.desc())
                )
                .scalars()
                .all()
            )

            if query_templates:
                detection_embedding = matcher.encode_crop(image_bytes=image_bytes, bbox=item.bbox)
                for template in query_templates:
                    try:
                        template_embedding = json.loads(template.embedding_json or "[]")
                    except json.JSONDecodeError:
                        continue

                    if not template_embedding:
                        continue

                    score = matcher.cosine_similarity(detection_embedding, template_embedding)
                    if score > best_score:
                        best_score = score
                        best_template = template

            final_score = round(best_score if best_template else item.confidence, 4)

            row = DetectionModel(
                task_id=task_id,
                type=item.label,
                x=item.bbox[0],
                y=item.bbox[1],
                w=item.bbox[2],
                h=item.bbox[3],
                score=final_score,
                result=_score_to_result(final_score),
                matched_template_url=best_template.image_url if best_template else "",
            )
            db.add(row)

        task.status = "done"
        db.commit()
    except RuntimeError as exc:
        task.status = "done"
        db.commit()
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return UploadOrderResponse(task_id=task_id)


@router.get("/result/{task_id}", response_model=TaskResultDTO)
def get_result(task_id: str, db: Session = Depends(get_db_session)) -> TaskResultDTO:
    task = db.get(TaskModel, task_id)
    if task is None:
        return TaskResultDTO(status="pending", detections=[])

    rows = (
        db.execute(select(DetectionModel).where(DetectionModel.task_id == task_id).order_by(DetectionModel.id.asc()))
        .scalars()
        .all()
    )
    return TaskResultDTO(status=task.status, detections=[_to_detection_dto(row) for row in rows])


@router.get("/tasks/{task_id}", response_model=UploadTaskDTO | None)
def get_task(task_id: str, db: Session = Depends(get_db_session)) -> UploadTaskDTO | None:
    task = db.get(TaskModel, task_id)
    if task is None:
        return None
    return UploadTaskDTO(
        task_id=task.task_id,
        file_name=task.file_name,
        image_url=task.image_url,
        status=task.status,
        created_at=_to_iso(task.created_at),
    )


@router.get("/tasks/latest", response_model=UploadTaskDTO | None)
def get_latest_task(db: Session = Depends(get_db_session)) -> UploadTaskDTO | None:
    task = db.execute(select(TaskModel).order_by(TaskModel.created_at.desc())).scalars().first()
    if task is None:
        return None
    return UploadTaskDTO(
        task_id=task.task_id,
        file_name=task.file_name,
        image_url=task.image_url,
        status=task.status,
        created_at=_to_iso(task.created_at),
    )


@router.post("/review", response_model=ReviewRecordDTO)
def review(payload: ReviewRequest, db: Session = Depends(get_db_session)) -> ReviewRecordDTO:
    if payload.result not in {"true", "false", "suspicious"}:
        raise HTTPException(status_code=400, detail="Invalid review result.")

    detection = db.get(DetectionModel, payload.detect_id)
    if detection is None:
        raise HTTPException(status_code=404, detail="Detection item not found.")

    detection.result = payload.result
    review_row = ReviewModel(detect_id=payload.detect_id, result=payload.result)
    db.add(review_row)
    db.commit()
    db.refresh(review_row)

    return ReviewRecordDTO(
        id=review_row.id,
        detect_id=review_row.detect_id,
        result=review_row.result,
        created_at=_to_iso(review_row.created_at),
    )


@router.get("/history", response_model=list[HistoryItemDTO])
def get_history(db: Session = Depends(get_db_session)) -> list[HistoryItemDTO]:
    tasks = db.execute(select(TaskModel).order_by(TaskModel.created_at.desc())).scalars().all()

    items: list[HistoryItemDTO] = []
    for task in tasks:
        detection_count = db.execute(
            select(func.count(DetectionModel.id)).where(DetectionModel.task_id == task.task_id)
        ).scalar_one()
        review_count = db.execute(
            select(func.count(ReviewModel.id))
            .join(DetectionModel, ReviewModel.detect_id == DetectionModel.id)
            .where(DetectionModel.task_id == task.task_id)
        ).scalar_one()

        items.append(
            HistoryItemDTO(
                id=task.task_id,
                created_at=_to_iso(task.created_at),
                status=task.status,
                detections=int(detection_count),
                reviews=int(review_count),
            )
        )
    return items


@router.post("/templates/rebuild-embeddings")
def rebuild_template_embeddings(
    db: Session = Depends(get_db_session),
    matcher: SiameseVectorMatcher = Depends(get_vector_matcher),
) -> dict[str, int]:
    templates = db.execute(select(TemplateModel).order_by(TemplateModel.id.asc())).scalars().all()

    total = len(templates)
    updated = 0
    skipped = 0

    for template in templates:
        if template.embedding_json:
            skipped += 1
            continue

        try:
            image_bytes = _read_template_bytes(template.image_url)
            embedding = matcher.encode_image(image_bytes)
            template.embedding_json = json.dumps(embedding, ensure_ascii=True)
            updated += 1
        except Exception:
            skipped += 1

    db.commit()
    return {
        "total": total,
        "updated": updated,
        "skipped": skipped,
    }


@router.post("/detect", response_model=DetectResponseDTO)
async def detect(
    file: UploadFile = File(...),
    imgsz: int | None = Query(default=None, ge=320, le=2048),
    conf: float | None = Query(default=None, ge=0.01, le=0.99),
    device: str | None = Query(default=None),
) -> DetectResponseDTO:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file must have a filename.")

    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files are supported.")

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        use_case = get_detect_use_case()
        result = use_case.execute(
            file_name=file.filename,
            image_bytes=image_bytes,
            imgsz=imgsz,
            conf=conf,
            device=device,
        )
        return _to_response_dto(result)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
