from datetime import datetime
import json
from pathlib import Path
from urllib.request import urlopen
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.bootstrap.config import get_settings
from app.bootstrap.dependencies import (
    get_db_session,
    get_detect_use_case,
    get_local_storage,
    get_stamp_ocr,
    get_vector_matcher,
)
from app.domain.detection.entities import Detection, DetectionResult
from app.infrastructure.ai.siamese_vector_matcher import PrototypePayload, SiameseVectorMatcher
from app.infrastructure.ai.stamp_ocr import StampOcrMatcher
from app.infrastructure.db.models import CustomerModel, DetectionModel, ReviewModel, TaskModel, TemplateModel
from app.infrastructure.storage.local_storage import LocalStorage
from app.interfaces.api.dto.business import (
    CustomerCreateRequest,
    CustomerDTO,
    CustomerStatsDTO,
    CustomerUpdateRequest,
    DetectionDTO,
    HistoryItemDTO,
    PendingReviewItemDTO,
    ReviewRecordDTO,
    ReviewRequest,
    TaskResultDTO,
    TemplateDTO,
    UploadOrderResponse,
    UploadTaskDTO,
)
from app.interfaces.api.dto.detect import DetectResponseDTO, DetectionItemDTO

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"message": "pong"}


def _to_iso(dt: datetime | None) -> str:
    if dt is None:
        return datetime.utcnow().isoformat()
    return dt.isoformat()


def _score_to_result(score: float, *, high: float = 0.85, low: float = 0.6) -> str:
    if score >= high:
        return "true"
    if score >= low:
        return "suspicious"
    return "false"


def _load_prototype_or_legacy(
    template: TemplateModel,
    matcher: SiameseVectorMatcher,
) -> PrototypePayload | None:
    """Load the new prototype payload, transparently upgrading legacy rows.

    Legacy rows only have a single `embedding_json` (pre-prototype era);
    we wrap that as a degenerate prototype so matching still works.
    """
    if template.prototype_json:
        try:
            data = json.loads(template.prototype_json)
        except json.JSONDecodeError:
            data = None
        if data:
            payload = PrototypePayload.from_dict(data)
            if payload is not None:
                return payload

    if template.embedding_json:
        try:
            embedding = json.loads(template.embedding_json)
        except json.JSONDecodeError:
            return None
        if not embedding:
            return None
        return matcher.build_prototype([embedding])

    return None


def _build_template_payload(
    matcher: SiameseVectorMatcher,
    image_bytes: bytes,
) -> PrototypePayload | None:
    """Encode K augmented variants of one template image and build its prototype."""
    variants = matcher.encode_image_variants(image_bytes)
    if not variants:
        return None
    return matcher.build_prototype(variants)


def _match_detection(
    *,
    item: Detection,
    image_bytes: bytes,
    customer: CustomerModel,
    db: Session,
    matcher: SiameseVectorMatcher,
    ocr: StampOcrMatcher,
) -> tuple[float, str, TemplateModel | None]:
    """Resolve a single detection against the customer's templates.

    Order of operations (cheap → expensive):
      1. Stamp OCR shortcut: read the perimeter text and match against the
         customer's registered name. Bypasses similarity entirely on success.
      2. Prototype matching: max-over-K cosine against each template's
         augmented embeddings, with adaptive thresholds derived from intra-
         template encoder stability.
      3. Fallback: when no template exists for this (customer, type), keep
         the detector's confidence as the score so the row is still useful.
    """
    # 1) Stamp OCR shortcut.
    if item.label == "stamp" and ocr.is_available:
        ocr_result = ocr.verify_stamp(
            image_bytes=image_bytes, bbox=item.bbox, customer_name=customer.name
        )
        if ocr_result.matched:
            ref_template = (
                db.execute(
                    select(TemplateModel)
                    .where(
                        TemplateModel.customer_id == customer.id,
                        TemplateModel.type == "stamp",
                    )
                    .order_by(TemplateModel.created_at.desc())
                )
                .scalars()
                .first()
            )
            return round(ocr_result.score, 4), "true", ref_template

    # 2) Prototype matching against same-type templates.
    templates = (
        db.execute(
            select(TemplateModel)
            .where(
                TemplateModel.customer_id == customer.id,
                TemplateModel.type == item.label,
            )
            .order_by(TemplateModel.created_at.desc())
        )
        .scalars()
        .all()
    )

    if templates:
        query_embedding = matcher.encode_crop(image_bytes=image_bytes, bbox=item.bbox)

        best_score = 0.0
        best_template: TemplateModel | None = None
        best_payload: PrototypePayload | None = None

        for template in templates:
            payload = _load_prototype_or_legacy(template, matcher)
            if payload is None:
                continue
            score = matcher.score_against_prototype(query_embedding, payload)
            if score > best_score:
                best_score = score
                best_template = template
                best_payload = payload

        if best_template is not None:
            high, low = matcher.adaptive_thresholds(best_payload)
            return (
                round(best_score, 4),
                _score_to_result(best_score, high=high, low=low),
                best_template,
            )

    # 3) No usable template → fall back to detector confidence as the score.
    return round(item.confidence, 4), _score_to_result(item.confidence), None


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


def _refresh_task_audit_state(db: Session, task_id: str) -> None:
    task = db.get(TaskModel, task_id)
    if task is None:
        return

    results = db.execute(
        select(DetectionModel.result).where(DetectionModel.task_id == task_id)
    ).scalars().all()

    if not results:
        task.status = "done"
        task.audit_result = None
        return

    if any(item == "suspicious" for item in results):
        task.status = "pending_review"
        task.audit_result = None
        return

    task.status = "done"
    task.audit_result = "false" if any(item == "false" for item in results) else "true"


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

    payload = _build_template_payload(matcher, image_bytes)
    if payload is None:
        raise HTTPException(status_code=400, detail="Failed to encode template image.")

    _, image_url = storage.save_image(image_bytes=image_bytes, original_name=file.filename or "template.jpg", category="templates")

    row = TemplateModel(
        customer_id=customer_id,
        type=type,
        image_url=image_url,
        # Keep `embedding_json` populated for backward compatibility with any
        # external reader; new query path uses `prototype_json`.
        embedding_json=json.dumps(payload.prototype, ensure_ascii=True),
        prototype_json=json.dumps(payload.to_dict(), ensure_ascii=True),
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
    customer_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db_session),
    storage: LocalStorage = Depends(get_local_storage),
    matcher: SiameseVectorMatcher = Depends(get_vector_matcher),
    ocr: StampOcrMatcher = Depends(get_stamp_ocr),
) -> UploadOrderResponse:
    customer = db.get(CustomerModel, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found.")

    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file must have a filename.")

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    task_id = f"task_{uuid4().hex[:12]}"
    _, image_url = storage.save_image(image_bytes=image_bytes, original_name=file.filename, category="orders")

    task = TaskModel(
        task_id=task_id,
        customer_id=customer_id,
        file_name=file.filename,
        image_url=image_url,
        status="running",
        audit_result=None,
    )
    db.add(task)
    db.commit()

    try:
        use_case = get_detect_use_case()
        detect_result = use_case.execute(file_name=file.filename, image_bytes=image_bytes)

        for item in detect_result.detections:
            score, result, matched_template = _match_detection(
                item=item,
                image_bytes=image_bytes,
                customer=customer,
                db=db,
                matcher=matcher,
                ocr=ocr,
            )

            row = DetectionModel(
                task_id=task_id,
                type=item.label,
                x=item.bbox[0],
                y=item.bbox[1],
                w=item.bbox[2],
                h=item.bbox[3],
                score=score,
                result=result,
                matched_template_url=matched_template.image_url if matched_template else "",
            )
            db.add(row)

        db.flush()
        _refresh_task_audit_state(db, task_id)
        db.commit()
    except RuntimeError as exc:
        task.status = "done"
        task.audit_result = None
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
    customer_name = None
    if task.customer_id is not None:
        customer = db.get(CustomerModel, task.customer_id)
        customer_name = customer.name if customer is not None else None

    return UploadTaskDTO(
        task_id=task.task_id,
        customer_id=task.customer_id,
        customer_name=customer_name,
        audit_result=task.audit_result,
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
    customer_name = None
    if task.customer_id is not None:
        customer = db.get(CustomerModel, task.customer_id)
        customer_name = customer.name if customer is not None else None

    return UploadTaskDTO(
        task_id=task.task_id,
        customer_id=task.customer_id,
        customer_name=customer_name,
        audit_result=task.audit_result,
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
    db.flush()
    _refresh_task_audit_state(db, detection.task_id)
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
    tasks = (
        db.execute(
            select(TaskModel)
            .where(TaskModel.status == "done", TaskModel.audit_result.is_not(None))
            .order_by(TaskModel.created_at.desc())
        )
        .scalars()
        .all()
    )

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
                result=task.audit_result or "false",
                detections=int(detection_count),
                reviews=int(review_count),
            )
        )
    return items


@router.get("/review/pending", response_model=list[PendingReviewItemDTO])
def get_pending_reviews(db: Session = Depends(get_db_session)) -> list[PendingReviewItemDTO]:
    rows = db.execute(
        select(
            TaskModel.task_id,
            TaskModel.created_at,
            DetectionModel.id,
            DetectionModel.type,
            DetectionModel.score,
            DetectionModel.result,
        )
        .join(DetectionModel, DetectionModel.task_id == TaskModel.task_id)
        .where(TaskModel.status == "pending_review")
        .where(DetectionModel.result == "suspicious")
        .order_by(TaskModel.created_at.desc(), DetectionModel.id.asc())
    ).all()

    return [
        PendingReviewItemDTO(
            task_id=task_id,
            task_created_at=_to_iso(task_created_at),
            detect_id=detect_id,
            type=detect_type,
            score=float(score),
            result=detect_result,
        )
        for task_id, task_created_at, detect_id, detect_type, score, detect_result in rows
    ]


@router.post("/templates/rebuild-embeddings")
def rebuild_template_embeddings(
    force: bool = Query(default=False),
    db: Session = Depends(get_db_session),
    matcher: SiameseVectorMatcher = Depends(get_vector_matcher),
) -> dict[str, int]:
    """Backfill / rebuild prototype payloads for every template.

    By default, rows that already have a `prototype_json` are skipped. Pass
    `?force=true` to re-encode everything (e.g. after swapping the Siamese
    weights or changing the augmentation pipeline).
    """
    templates = db.execute(select(TemplateModel).order_by(TemplateModel.id.asc())).scalars().all()

    total = len(templates)
    updated = 0
    skipped = 0

    for template in templates:
        if template.prototype_json and not force:
            skipped += 1
            continue

        try:
            image_bytes = _read_template_bytes(template.image_url)
            payload = _build_template_payload(matcher, image_bytes)
            if payload is None:
                skipped += 1
                continue
            template.prototype_json = json.dumps(payload.to_dict(), ensure_ascii=True)
            template.embedding_json = json.dumps(payload.prototype, ensure_ascii=True)
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
