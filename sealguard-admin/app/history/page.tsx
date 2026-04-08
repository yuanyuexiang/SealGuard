"use client";

import { useQuery } from "@tanstack/react-query";
import { Button, Card, Space, Table, Tag, Typography } from "antd";

import { getHistory } from "@/services/mockApi";

function statusColor(status: "pending" | "running" | "done") {
  if (status === "done") return "success";
  if (status === "running") return "processing";
  return "default";
}

export default function HistoryPage() {
  const historyQuery = useQuery({
    queryKey: ["history"],
    queryFn: getHistory,
  });

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Card className="hero-card">
        <Typography.Title level={3}>历史记录</Typography.Title>
        <Typography.Paragraph>
          查看任务处理状态、检测数量和审核覆盖情况。
        </Typography.Paragraph>
      </Card>

      <Card title="任务列表">
        <Table
          rowKey="id"
          loading={historyQuery.isLoading}
          dataSource={historyQuery.data ?? []}
          pagination={{ pageSize: 8 }}
          columns={[
            { title: "货单ID", dataIndex: "id" },
            {
              title: "时间",
              dataIndex: "created_at",
              render: (value: string) => new Date(value).toLocaleString(),
            },
            {
              title: "状态",
              dataIndex: "status",
              render: (value: "pending" | "running" | "done") => (
                <Tag color={statusColor(value)}>{value}</Tag>
              ),
            },
            { title: "检测项", dataIndex: "detections" },
            { title: "审核数", dataIndex: "reviews" },
            {
              title: "操作",
              render: () => <Button type="link">查看</Button>,
            },
          ]}
        />
      </Card>
    </Space>
  );
}
