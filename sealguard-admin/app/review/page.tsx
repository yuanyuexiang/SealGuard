"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, Empty, Segmented, Space, Typography, message } from "antd";
import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";

import DetectionCanvas from "@/components/DetectionCanvas";
import ResultTag from "@/components/ResultTag";
import {
  getPendingReviews,
  getResult,
  getTask,
  reviewDetection,
} from "@/services/mockApi";
import type { ReviewResult } from "@/types/domain";

export default function ReviewPage() {
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();
  const defaultTaskId = searchParams.get("taskId");
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(defaultTaskId);
  const [selectedDetectId, setSelectedDetectId] = useState<number | null>(null);

  const pendingQuery = useQuery({
    queryKey: ["pending-reviews"],
    queryFn: getPendingReviews,
  });

  const pendingTaskOptions = useMemo(() => {
    const countMap = new Map<string, number>();
    for (const item of pendingQuery.data ?? []) {
      countMap.set(item.task_id, (countMap.get(item.task_id) ?? 0) + 1);
    }

    return [...countMap.entries()].map(([id, count]) => ({
      label: `${id}（待审核 ${count} 项）`,
      value: id,
    }));
  }, [pendingQuery.data]);

  const taskId = selectedTaskId ?? pendingTaskOptions[0]?.value ?? null;

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

  const suspiciousDetections = useMemo(
    () => (resultQuery.data?.detections ?? []).filter((item) => item.result === "suspicious"),
    [resultQuery.data],
  );

  const activeDetection = useMemo(
    () =>
      suspiciousDetections.find((item) => item.id === selectedDetectId) ??
      suspiciousDetections[0],
    [suspiciousDetections, selectedDetectId],
  );

  const reviewMutation = useMutation({
    mutationFn: ({ detectId, result }: { detectId: number; result: ReviewResult }) =>
      reviewDetection({ detect_id: detectId, result }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["review-result", taskId] }),
        queryClient.invalidateQueries({ queryKey: ["pending-reviews"] }),
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
          仅处理可疑项。历史记录页只展示最终一致/不一致结果。
        </Typography.Paragraph>
      </Card>

      <Card title="待审核任务队列">
        {!pendingTaskOptions.length && !pendingQuery.isLoading && <Empty description="当前没有待审核任务" />}
        {!!pendingTaskOptions.length && (
          <Space direction="vertical" style={{ width: "100%" }}>
            <Typography.Text type="secondary">
              已检出待审核任务 {pendingTaskOptions.length} 个
            </Typography.Text>
            <Segmented
              options={pendingTaskOptions}
              value={taskId ?? undefined}
              onChange={(value) => {
                setSelectedTaskId(String(value));
                setSelectedDetectId(null);
              }}
            />
          </Space>
        )}
      </Card>

      {!taskId && (
        <Card>
          <Empty description="暂无可审核任务，请先到上传页创建任务" />
        </Card>
      )}

      {taskId && (
        <Card>
          <Space>
            <Typography.Text>任务ID：</Typography.Text>
            <Typography.Text strong>{taskId}</Typography.Text>
            <Typography.Text type="secondary">客户：{taskQuery.data?.customer_name ?? "-"}</Typography.Text>
          </Space>
        </Card>
      )}

      {taskId && !resultQuery.isLoading && suspiciousDetections.length === 0 && (
        <Card>
          <Empty description="该任务暂无可疑项，无需人工审核" />
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

              {suspiciousDetections.length > 1 && (
                <Segmented
                  options={suspiciousDetections.map((item) => ({
                    label: `${item.type}-${item.id}`,
                    value: item.id,
                  }))}
                  value={activeDetection.id}
                  onChange={(value) => setSelectedDetectId(Number(value))}
                />
              )}

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
