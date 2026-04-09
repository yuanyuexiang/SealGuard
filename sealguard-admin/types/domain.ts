export type ReviewResult = "true" | "false" | "suspicious";

export type DetectionType = "signature" | "stamp";

export type Customer = {
  id: number;
  name: string;
  template_total?: number;
  signature_templates?: number;
  stamp_templates?: number;
};

export type CustomerStats = {
  customer_id: number;
  customer_name: string;
  template_total: number;
  signature_templates: number;
  stamp_templates: number;
};

export type Template = {
  id: number;
  customer_id: number;
  type: DetectionType;
  image_url: string;
  created_at: string;
};

export type Detection = {
  id: number;
  task_id: string;
  type: DetectionType;
  bbox: [number, number, number, number];
  score: number;
  result: ReviewResult;
  matched_template_url: string;
};

export type UploadTask = {
  task_id: string;
  customer_id?: number | null;
  customer_name?: string | null;
  audit_result?: ReviewResult | null;
  file_name: string;
  image_url: string;
  status: "pending" | "running" | "pending_review" | "done";
  created_at: string;
};

export type HistoryItem = {
  id: string;
  created_at: string;
  result: "true" | "false" | null;
  detections: number;
  reviews: number;
};

export type TaskResult = {
  status: UploadTask["status"];
  detections: Detection[];
};

export type ReviewRecord = {
  id: number;
  detect_id: number;
  result: ReviewResult;
  created_at: string;
};

export type DetectItem = {
  id: number;
  type: string;
  confidence: number;
  bbox: [number, number, number, number];
};

export type DetectResponse = {
  file_name: string;
  image_width: number;
  image_height: number;
  model_name: string;
  detections: DetectItem[];
};

export type PendingReviewItem = {
  task_id: string;
  task_created_at: string;
  detect_id: number;
  type: DetectionType;
  score: number;
  result: ReviewResult;
};
