"use client";

import { Tag } from "antd";

import type { ReviewResult } from "@/types/domain";

export default function ResultTag({ result }: { result: ReviewResult }) {
  if (result === "true") return <Tag color="success">一致</Tag>;
  if (result === "false") return <Tag color="error">不一致</Tag>;
  return <Tag color="warning">可疑</Tag>;
}
