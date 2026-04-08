import type {
  Customer,
  Detection,
  ReviewRecord,
  ReviewResult,
  TaskResult,
  Template,
  UploadTask,
} from "@/types/domain";

let customerId = 3;
let templateId = 3;
let detectId = 3;
let reviewId = 1;

const nowIso = () => new Date().toISOString();

const delay = (ms = 400) => new Promise((resolve) => setTimeout(resolve, ms));

const customers: Customer[] = [
  { id: 1, name: "可口可乐华南配送中心" },
  { id: 2, name: "可口可乐华东供应链" },
];

const templates: Template[] = [
  {
    id: 1,
    customer_id: 1,
    type: "signature",
    image_url: "https://images.unsplash.com/photo-1545239351-1141bd82e8a6?q=80&w=1200&auto=format&fit=crop",
    created_at: nowIso(),
  },
  {
    id: 2,
    customer_id: 1,
    type: "stamp",
    image_url: "https://images.unsplash.com/photo-1455390582262-044cdead277a?q=80&w=1200&auto=format&fit=crop",
    created_at: nowIso(),
  },
];

const tasks: UploadTask[] = [];
const detectionsByTask = new Map<string, Detection[]>();
const reviews: ReviewRecord[] = [];

function buildMockDetections(taskId: string): Detection[] {
  const base: Detection[] = [
    {
      id: detectId++,
      task_id: taskId,
      type: "signature",
      bbox: [120, 260, 180, 80],
      score: 0.91,
      result: "true",
      matched_template_url:
        "https://images.unsplash.com/photo-1455390582262-044cdead277a?q=80&w=1200&auto=format&fit=crop",
    },
    {
      id: detectId++,
      task_id: taskId,
      type: "stamp",
      bbox: [460, 190, 150, 120],
      score: 0.67,
      result: "suspicious",
      matched_template_url:
        "https://images.unsplash.com/photo-1545239351-1141bd82e8a6?q=80&w=1200&auto=format&fit=crop",
    },
  ];
  return base;
}

export async function getCustomers(): Promise<Customer[]> {
  await delay();
  return [...customers];
}

export async function createCustomer(name: string): Promise<Customer> {
  await delay();
  const customer = { id: customerId++, name };
  customers.unshift(customer);
  return customer;
}

export async function getTemplates(customerIdValue: number): Promise<Template[]> {
  await delay();
  return templates.filter((item) => item.customer_id === customerIdValue);
}

export async function uploadTemplate(params: {
  customerIdValue: number;
  type: "signature" | "stamp";
  fileName: string;
}): Promise<Template> {
  await delay(600);
  const template: Template = {
    id: templateId++,
    customer_id: params.customerIdValue,
    type: params.type,
    image_url:
      params.type === "signature"
        ? "https://images.unsplash.com/photo-1521791136064-7986c2920216?q=80&w=1200&auto=format&fit=crop"
        : "https://images.unsplash.com/photo-1582719478250-c89cae4dc85b?q=80&w=1200&auto=format&fit=crop",
    created_at: nowIso(),
  };
  templates.unshift(template);
  return template;
}

export async function deleteTemplate(templateIdValue: number): Promise<void> {
  await delay();
  const index = templates.findIndex((item) => item.id === templateIdValue);
  if (index >= 0) {
    templates.splice(index, 1);
  }
}

export async function uploadOrder(fileName: string): Promise<{ task_id: string }> {
  await delay(500);
  const task_id = `task_${Date.now()}`;
  tasks.unshift({
    task_id,
    file_name: fileName,
    image_url:
      "https://images.unsplash.com/photo-1566576912321-d58ddd7a6088?q=80&w=1200&auto=format&fit=crop",
    status: "running",
    created_at: nowIso(),
  });
  detectionsByTask.set(task_id, buildMockDetections(task_id));

  setTimeout(() => {
    const task = tasks.find((item) => item.task_id === task_id);
    if (task) task.status = "done";
  }, 2200);

  return { task_id };
}

export async function getResult(taskId: string): Promise<TaskResult> {
  await delay(300);
  const task = tasks.find((item) => item.task_id === taskId);
  if (!task) {
    return { status: "pending", detections: [] };
  }
  return {
    status: task.status,
    detections: detectionsByTask.get(taskId) ?? [],
  };
}

export async function getTask(taskId: string): Promise<UploadTask | null> {
  await delay(150);
  return tasks.find((item) => item.task_id === taskId) ?? null;
}

export async function getLatestTask(): Promise<UploadTask | null> {
  await delay(120);
  return tasks[0] ?? null;
}

export async function reviewDetection(params: {
  detect_id: number;
  result: ReviewResult;
}): Promise<ReviewRecord> {
  await delay(250);
  for (const detections of detectionsByTask.values()) {
    const target = detections.find((item) => item.id === params.detect_id);
    if (target) {
      target.result = params.result;
      break;
    }
  }

  const record: ReviewRecord = {
    id: reviewId++,
    detect_id: params.detect_id,
    result: params.result,
    created_at: nowIso(),
  };
  reviews.unshift(record);
  return record;
}

export async function getHistory(): Promise<
  Array<{
    id: string;
    created_at: string;
    status: UploadTask["status"];
    detections: number;
    reviews: number;
  }>
> {
  await delay();
  return tasks.map((task) => {
    const detections = detectionsByTask.get(task.task_id) ?? [];
    const reviewCount = detections.filter((d) =>
      reviews.some((review) => review.detect_id === d.id),
    ).length;

    return {
      id: task.task_id,
      created_at: task.created_at,
      status: task.status,
      detections: detections.length,
      reviews: reviewCount,
    };
  });
}
