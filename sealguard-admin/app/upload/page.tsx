"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Alert, Button, Card, Empty, Select, Space, Typography, Upload, message } from "antd";
import type { UploadProps } from "antd";
import { useEffect, useState } from "react";

import DetectionCanvas from "@/components/DetectionCanvas";
import ResultTag from "@/components/ResultTag";
import { getCustomers, getResult, getTask, uploadOrder } from "@/services/mockApi";

export default function UploadPage() {
  const [taskId, setTaskId] = useState<string | null>(null);
  const [selectedCustomerId, setSelectedCustomerId] = useState<number | null>(null);

  const customersQuery = useQuery({
    queryKey: ["customers"],
    queryFn: getCustomers,
  });

  useEffect(() => {
    if (selectedCustomerId) {
      return;
    }
    const first = customersQuery.data?.[0];
    if (first) {
      setSelectedCustomerId(first.id);
    }
  }, [customersQuery.data, selectedCustomerId]);

  const uploadMutation = useMutation({
    mutationFn: ({ customerId, file, fileName }: { customerId: number; file: Blob; fileName: string }) =>
      uploadOrder({ customerIdValue: customerId, file, fileName }),
    onSuccess: (data) => setTaskId(data.task_id),
    onError: (error: Error) => {
      message.error(error.message || "上传失败");
    },
  });

  const resultQuery = useQuery({
    queryKey: ["result", taskId],
    queryFn: () => getResult(taskId as string),
    enabled: Boolean(taskId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && status !== "done" ? 2000 : false;
    },
  });

  const taskQuery = useQuery({
    queryKey: ["task", taskId],
    queryFn: () => getTask(taskId as string),
    enabled: Boolean(taskId),
  });

  const uploadProps: UploadProps = {
    multiple: false,
    showUploadList: false,
    customRequest: async (options) => {
      try {
        if (!selectedCustomerId) {
          throw new Error("请先选择客户");
        }

        if (typeof options.file === "string") {
          throw new Error("Invalid upload file");
        }
        const fileName = "name" in options.file ? options.file.name : `order-${Date.now()}.jpg`;
        const candidate =
          "originFileObj" in options.file && options.file.originFileObj
            ? options.file.originFileObj
            : options.file;
        if (!(candidate instanceof Blob)) {
          throw new Error("Invalid upload payload");
        }
        const file: Blob = candidate;
        const response = await uploadMutation.mutateAsync({
          customerId: selectedCustomerId,
          file,
          fileName,
        });
        options.onSuccess?.(response, options.file);
      } catch (error) {
        if (error instanceof Error) {
          options.onError?.(error);
        } else {
          options.onError?.(new Error("upload failed"));
        }
      }
    },
  };

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Card className="hero-card">
        <Typography.Title level={3}>货单上传与自动比对</Typography.Title>
        <Typography.Paragraph>
          上传货单后，系统自动检测签字与印章并进行相似度比对。
        </Typography.Paragraph>
      </Card>

      <Card title="上传货单">
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Select
            placeholder="请选择客户"
            value={selectedCustomerId ?? undefined}
            onChange={(value) => setSelectedCustomerId(value)}
            loading={customersQuery.isLoading}
            options={(customersQuery.data ?? []).map((customer) => ({
              label: customer.name,
              value: customer.id,
            }))}
            style={{ maxWidth: 360, width: "100%" }}
          />
          {!customersQuery.isLoading && !(customersQuery.data?.length ?? 0) && (
            <Alert
              type="warning"
              showIcon
              message="暂无可用客户"
              description="请先在客户管理中创建客户并上传模板，再执行货单比对。"
            />
          )}
        <Upload.Dragger {...uploadProps} accept="image/*">
          <p>拖拽图片到此，或点击上传货单</p>
          <Button
            type="primary"
            loading={uploadMutation.isPending}
            disabled={uploadMutation.isPending || !selectedCustomerId}
          >
            立即上传
          </Button>
        </Upload.Dragger>
        </Space>
      </Card>

      <Card title="任务状态">
        {!taskId && <Empty description="请先上传货单" />}
        {taskId && (
          <Space direction="vertical" style={{ width: "100%" }}>
            <Typography.Text>任务ID：{taskId}</Typography.Text>
            <Typography.Text>
              客户：{taskQuery.data?.customer_name ?? customersQuery.data?.find((c) => c.id === selectedCustomerId)?.name ?? "-"}
            </Typography.Text>
            <Typography.Text>
              当前状态：{resultQuery.data?.status ?? "pending"}
            </Typography.Text>
          </Space>
        )}
      </Card>

      <Card title="检测结果展示">
        {!taskQuery.data?.image_url && <Empty description="暂无检测结果" />}
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
