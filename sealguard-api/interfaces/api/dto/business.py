from pydantic import BaseModel


class CustomerDTO(BaseModel):
    id: int
    name: str
    template_total: int = 0
    signature_templates: int = 0
    stamp_templates: int = 0


class CustomerCreateRequest(BaseModel):
    name: str


class CustomerUpdateRequest(BaseModel):
    name: str


class CustomerStatsDTO(BaseModel):
    customer_id: int
    customer_name: str
    template_total: int
    signature_templates: int
    stamp_templates: int


class TemplateDTO(BaseModel):
    id: int
    customer_id: int
    type: str
    image_url: str
    created_at: str


class UploadOrderResponse(BaseModel):
    task_id: str


class UploadTaskDTO(BaseModel):
    task_id: str
    customer_id: int | None = None
    customer_name: str | None = None
    file_name: str
    image_url: str
    status: str
    created_at: str


class DetectionDTO(BaseModel):
    id: int
    task_id: str
    type: str
    bbox: list[float]
    score: float
    result: str
    matched_template_url: str


class TaskResultDTO(BaseModel):
    status: str
    detections: list[DetectionDTO]


class ReviewRequest(BaseModel):
    detect_id: int
    result: str


class ReviewRecordDTO(BaseModel):
    id: int
    detect_id: int
    result: str
    created_at: str


class HistoryItemDTO(BaseModel):
    id: str
    created_at: str
    status: str
    detections: int
    reviews: int
