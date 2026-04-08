export type ReviewResult = "true" | "false" | "suspicious";

export type DetectionType = "signature" | "stamp";

export type Customer = {
  id: number;
  name: string;
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
  file_name: string;
  image_url: string;
  status: "pending" | "running" | "done";
  created_at: string;
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
