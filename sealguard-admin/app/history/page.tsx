"use client";

import { useQuery } from "@tanstack/react-query";
import { Button, Card, Segmented, Space, Table, Tag, Typography } from "antd";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { getHistory } from "@/services/mockApi";
import type { HistoryItem } from "@/types/domain";

function resultColor(result: "true" | "false" | null) {
  if (result === null) return "default";
  if (result === "true") return "success";
  return "error";
}

function resultLabel(result: "true" | "false" | null) {
  if (result === "true") return "一致";
  if (result === "false") return "不一致";
  return "待回填";
}

export default function HistoryPage() {
  const router = useRouter();
  const [resultFilter, setResultFilter] = useState<"all" | "true" | "false">("all");

  const historyQuery = useQuery({
    queryKey: ["history"],
    queryFn: getHistory,
  });

  const filteredHistory = useMemo(() => {
    const rows = historyQuery.data ?? [];
    if (resultFilter === "all") {
      return rows;
    }
    return rows.filter((item) => item.result === resultFilter);
  }, [historyQuery.data, resultFilter]);

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Card className="hero-card">
        <Typography.Title level={3}>历史记录</Typography.Title>
        <Typography.Paragraph>
          仅保留最终审核结论：一致 / 不一致。
        </Typography.Paragraph>
      </Card>

      <Card title="任务列表">
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Segmented
            options={[
              { label: "全部", value: "all" },
              { label: "一致", value: "true" },
              { label: "不一致", value: "false" },
            ]}
            value={resultFilter}
            onChange={(value) => setResultFilter(value as "all" | "true" | "false")}
          />

        <Table
          rowKey="id"
          loading={historyQuery.isLoading}
          dataSource={filteredHistory}
          pagination={{ pageSize: 8 }}
          columns={[
            { title: "货单ID", dataIndex: "id" },
            {
              title: "时间",
              dataIndex: "created_at",
              render: (value: string) => new Date(value).toLocaleString(),
            },
            {
              title: "审核结果",
              dataIndex: "result",
              render: (value: "true" | "false" | null) => (
                <Tag color={resultColor(value)}>{resultLabel(value)}</Tag>
              ),
            },
            { title: "检测项", dataIndex: "detections" },
            { title: "审核数", dataIndex: "reviews" },
            {
              title: "操作",
              render: (_: unknown, record: HistoryItem) => (
                <Button type="link" onClick={() => router.push(`/history/${record.id}`)}>
                  查看详情
                </Button>
              ),
            },
          ]}
        />
        </Space>
      </Card>
    </Space>
  );
}
