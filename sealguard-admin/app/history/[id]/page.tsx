"use client";

import { useQuery } from "@tanstack/react-query";
import { Button, Card, Empty, Space, Typography } from "antd";
import Link from "next/link";
import { useParams } from "next/navigation";

import DetectionCanvas from "@/components/DetectionCanvas";
import ResultTag from "@/components/ResultTag";
import { getResult, getTask } from "@/services/mockApi";

export default function HistoryDetailPage() {
  const params = useParams<{ id: string }>();
  const taskId = params.id;

  const taskQuery = useQuery({
    queryKey: ["history-task", taskId],
    queryFn: () => getTask(taskId),
    enabled: Boolean(taskId),
  });

  const resultQuery = useQuery({
    queryKey: ["history-result", taskId],
    queryFn: () => getResult(taskId),
    enabled: Boolean(taskId),
  });

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Card className="hero-card">
        <Typography.Title level={3}>历史任务详情</Typography.Title>
        <Typography.Paragraph>
          仅查看任务检测结果与处理状态，不在此页直接提交审核。
        </Typography.Paragraph>
      </Card>

      <Card title="任务信息">
        {!taskQuery.data && !taskQuery.isLoading && <Empty description="任务不存在" />}
        {taskQuery.data && (
          <Space direction="vertical" style={{ width: "100%" }}>
            <Typography.Text>任务ID：{taskQuery.data.task_id}</Typography.Text>
            <Typography.Text>客户：{taskQuery.data.customer_name ?? "-"}</Typography.Text>
            <Typography.Text>状态：{taskQuery.data.status}</Typography.Text>
            <Typography.Text>
              最终审核结论：
              {taskQuery.data.audit_result === "true"
                ? "一致"
                : taskQuery.data.audit_result === "false"
                  ? "不一致"
                  : "-"}
            </Typography.Text>
            <Typography.Text>创建时间：{new Date(taskQuery.data.created_at).toLocaleString()}</Typography.Text>
            <Link href="/history">
              <Button>返回历史记录</Button>
            </Link>
          </Space>
        )}
      </Card>

      <Card title="检测结果">
        {!taskQuery.data?.image_url && <Empty description="暂无图片结果" />}
        {taskQuery.data?.image_url && resultQuery.data && (
          <Space direction="vertical" style={{ width: "100%" }}>
            <DetectionCanvas imageUrl={taskQuery.data.image_url} detections={resultQuery.data.detections} />
            <div className="result-grid">
              {resultQuery.data.detections.map((item) => (
                <Card key={item.id} size="small">
                  <Space>
                    <Typography.Text strong>{item.type}</Typography.Text>
                    <ResultTag result={item.result} />
                    <Typography.Text>score: {item.score.toFixed(2)}</Typography.Text>
                  </Space>
                </Card>
              ))}
            </div>
          </Space>
        )}
      </Card>
    </Space>
  );
}
