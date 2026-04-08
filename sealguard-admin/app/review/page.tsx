"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, Empty, Space, Typography, message } from "antd";
import { useMemo } from "react";

import DetectionCanvas from "@/components/DetectionCanvas";
import ResultTag from "@/components/ResultTag";
import {
  getLatestTask,
  getResult,
  getTask,
  reviewDetection,
} from "@/services/mockApi";
import type { ReviewResult } from "@/types/domain";

export default function ReviewPage() {
  const queryClient = useQueryClient();

  const latestTaskQuery = useQuery({
    queryKey: ["latest-task"],
    queryFn: getLatestTask,
  });

  const taskId = latestTaskQuery.data?.task_id;

  const resultQuery = useQuery({
    queryKey: ["review-result", taskId],
    queryFn: () => getResult(taskId as string),
    enabled: Boolean(taskId),
  });

  const taskQuery = useQuery({
    queryKey: ["review-task", taskId],
    queryFn: () => getTask(taskId as string),
    enabled: Boolean(taskId),
  });

  const activeDetection = useMemo(() => resultQuery.data?.detections?.[0], [resultQuery.data]);

  const reviewMutation = useMutation({
    mutationFn: ({ detectId, result }: { detectId: number; result: ReviewResult }) =>
      reviewDetection({ detect_id: detectId, result }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["review-result", taskId] }),
        queryClient.invalidateQueries({ queryKey: ["history"] }),
      ]);
      message.success("审核已提交");
    },
  });

  const submit = async (result: ReviewResult) => {
    if (!activeDetection) return;
    await reviewMutation.mutateAsync({ detectId: activeDetection.id, result });
  };

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Card className="hero-card">
        <Typography.Title level={3}>人工审核中心</Typography.Title>
        <Typography.Paragraph>
          对 AI 比对结果进行最终确认，保证核验质量与审计可追溯。
        </Typography.Paragraph>
      </Card>

      {!taskId && (
        <Card>
          <Empty description="暂无可审核任务，请先到上传页创建任务" />
        </Card>
      )}

      {taskId && taskQuery.data?.image_url && activeDetection && (
        <>
          <Card title="检测图 vs 模板图">
            <div className="review-grid">
              <div>
                <Typography.Text strong>检测图</Typography.Text>
                <DetectionCanvas
                  imageUrl={taskQuery.data.image_url}
                  detections={resultQuery.data?.detections ?? []}
                />
              </div>
              <div>
                <Typography.Text strong>匹配模板</Typography.Text>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={activeDetection.matched_template_url}
                  alt="matched template"
                  className="review-template-image"
                />
              </div>
            </div>
          </Card>

          <Card title="审核操作">
            <Space direction="vertical" size={12}>
              <Space>
                <Typography.Text>当前目标：</Typography.Text>
                <Typography.Text strong>{activeDetection.type}</Typography.Text>
                <Typography.Text>相似度：{activeDetection.score.toFixed(2)}</Typography.Text>
                <ResultTag result={activeDetection.result} />
              </Space>
              <Space wrap>
                <Button type="primary" onClick={() => submit("true")} loading={reviewMutation.isPending}>
                  一致
                </Button>
                <Button danger onClick={() => submit("false")} loading={reviewMutation.isPending}>
                  不一致
                </Button>
                <Button
                  onClick={() => submit("suspicious")}
                  loading={reviewMutation.isPending}
                  style={{ borderColor: "#f08c00", color: "#f08c00" }}
                >
                  可疑
                </Button>
              </Space>
            </Space>
          </Card>
        </>
      )}
    </Space>
  );
}
