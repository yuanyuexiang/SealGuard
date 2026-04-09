import type {
  Customer,
  CustomerStats,
  DetectResponse,
  HistoryItem,
  PendingReviewItem,
  ReviewRecord,
  ReviewResult,
  TaskResult,
  Template,
  UploadTask,
} from "@/types/domain";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/backend";

type ApiErrorPayload = {
  detail?: string;
};

function normalizeImageUrl(url: string): string {
  if (!url) return "";
  if (/^https?:\/\//i.test(url)) return url;
  return `${API_BASE}${url.startsWith("/") ? "" : "/"}${url}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });

  if (!response.ok) {
    let detail = `Request failed: ${response.status}`;
    try {
      const errorPayload = (await response.json()) as ApiErrorPayload;
      if (errorPayload.detail) {
        detail = errorPayload.detail;
      }
    } catch {
      // ignore JSON parse errors for non-JSON responses.
    }
    throw new Error(detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export async function getCustomers(): Promise<Customer[]> {
  return request<Customer[]>("/api/customers");
}

export async function createCustomer(name: string): Promise<Customer> {
  return request<Customer>("/api/customers", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function updateCustomer(customerIdValue: number, name: string): Promise<Customer> {
  return request<Customer>(`/api/customers/${customerIdValue}`, {
    method: "PUT",
    body: JSON.stringify({ name }),
  });
}

export async function deleteCustomer(customerIdValue: number): Promise<void> {
  await request<{ status: string }>(`/api/customers/${customerIdValue}`, {
    method: "DELETE",
  });
}

export async function getCustomerStats(customerIdValue: number): Promise<CustomerStats> {
  return request<CustomerStats>(`/api/customers/${customerIdValue}/stats`);
}

export async function getTemplates(customerIdValue: number): Promise<Template[]> {
  const data = await request<Template[]>(`/api/templates?customer_id=${customerIdValue}`);
  return data.map((item) => ({
    ...item,
    image_url: normalizeImageUrl(item.image_url),
  }));
}

export async function uploadTemplate(params: {
  customerIdValue: number;
  type: "signature" | "stamp";
  file: Blob;
  fileName: string;
}): Promise<Template> {
  const formData = new FormData();
  formData.append("customer_id", String(params.customerIdValue));
  formData.append("type", params.type);
  formData.append("file", params.file, params.fileName);

  const response = await fetch(`${API_BASE}/api/templates/upload`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const errorPayload = (await response.json().catch(() => ({}))) as ApiErrorPayload;
    throw new Error(errorPayload.detail ?? `Upload template failed: ${response.status}`);
  }

  const template = (await response.json()) as Template;
  return {
    ...template,
    image_url: normalizeImageUrl(template.image_url),
  };
}

export async function deleteTemplate(templateIdValue: number): Promise<void> {
  await request<{ status: string }>(`/api/templates/${templateIdValue}`, {
    method: "DELETE",
  });
}

export async function uploadOrder(
  params: { customerIdValue: number; file: Blob; fileName: string },
): Promise<{ task_id: string }> {
  const formData = new FormData();
  formData.append("customer_id", String(params.customerIdValue));
  formData.append("file", params.file, params.fileName);

  const response = await fetch(`${API_BASE}/api/upload`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const errorPayload = (await response.json().catch(() => ({}))) as ApiErrorPayload;
    throw new Error(errorPayload.detail ?? `Upload order failed: ${response.status}`);
  }

  return (await response.json()) as { task_id: string };
}

export async function detectImage(file: Blob, fileName: string): Promise<DetectResponse> {
  const formData = new FormData();
  formData.append("file", file, fileName);

  const response = await fetch(`${API_BASE}/api/detect`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const errorPayload = (await response.json().catch(() => ({}))) as ApiErrorPayload;
    throw new Error(errorPayload.detail ?? `Detect image failed: ${response.status}`);
  }

  return (await response.json()) as DetectResponse;
}

export async function getResult(taskId: string): Promise<TaskResult> {
  const data = await request<TaskResult>(`/api/result/${taskId}`);
  return {
    ...data,
    detections: data.detections.map((item) => ({
      ...item,
      matched_template_url: normalizeImageUrl(item.matched_template_url),
    })),
  };
}

export async function getTask(taskId: string): Promise<UploadTask | null> {
  const data = await request<UploadTask | null>(`/api/tasks/${taskId}`);
  if (!data) return null;
  return {
    ...data,
    image_url: normalizeImageUrl(data.image_url),
  };
}

export async function getLatestTask(): Promise<UploadTask | null> {
  const data = await request<UploadTask | null>("/api/tasks/latest");
  if (!data) return null;
  return {
    ...data,
    image_url: normalizeImageUrl(data.image_url),
  };
}

export async function reviewDetection(params: {
  detect_id: number;
  result: ReviewResult;
}): Promise<ReviewRecord> {
  return request<ReviewRecord>("/api/review", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function getHistory(): Promise<
  HistoryItem[]
> {
  const rows = await request<Array<Record<string, unknown>>>("/api/history");
  return rows.map((row) => {
    const raw = row.result;
    const result = raw === "true" || raw === "false" ? raw : null;
    return {
      id: String(row.id ?? ""),
      created_at: String(row.created_at ?? ""),
      result,
      detections: Number(row.detections ?? 0),
      reviews: Number(row.reviews ?? 0),
    } satisfies HistoryItem;
  });
}

export async function getPendingReviews(): Promise<PendingReviewItem[]> {
  return request<PendingReviewItem[]>("/api/review/pending");
}
