"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Button,
  Card,
  Empty,
  Popconfirm,
  Segmented,
  Space,
  Typography,
  Upload,
  message,
} from "antd";
import type { UploadProps } from "antd";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";

import { deleteTemplate, getCustomers, getTemplates, uploadTemplate } from "@/services/mockApi";
import type { DetectionType } from "@/types/domain";

export default function CustomerDetailPage() {
  const params = useParams<{ id: string }>();
  const customerId = Number(params.id);
  const queryClient = useQueryClient();
  const [templateType, setTemplateType] = useState<DetectionType>("signature");

  const customersQuery = useQuery({ queryKey: ["customers"], queryFn: getCustomers });
  const templatesQuery = useQuery({
    queryKey: ["templates", customerId],
    queryFn: () => getTemplates(customerId),
  });

  const uploadMutation = useMutation({
    mutationFn: ({ file, fileName }: { file: Blob; fileName: string }) =>
      uploadTemplate({ customerIdValue: customerId, type: templateType, file, fileName }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["templates", customerId] });
      message.success("模板上传成功");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (templateId: number) => deleteTemplate(templateId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["templates", customerId] });
      message.success("模板已删除");
    },
  });

  const customer = useMemo(
    () => customersQuery.data?.find((item) => item.id === customerId),
    [customersQuery.data, customerId],
  );

  const uploadProps: UploadProps = {
    multiple: false,
    showUploadList: false,
    customRequest: async (options) => {
      try {
        if (typeof options.file === "string") {
          throw new Error("Invalid upload file");
        }
        const fileName = "name" in options.file ? options.file.name : `template-${Date.now()}.jpg`;
        const candidate =
          "originFileObj" in options.file && options.file.originFileObj
            ? options.file.originFileObj
            : options.file;
        if (!(candidate instanceof Blob)) {
          throw new Error("Invalid upload payload");
        }
        const file: Blob = candidate;
        await uploadMutation.mutateAsync({ file, fileName });
        options.onSuccess?.({}, options.file);
      } catch {
        options.onError?.(new Error("upload failed"));
      }
    },
  };

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Card className="hero-card">
        <Typography.Title level={3}>{customer?.name ?? "客户详情"}</Typography.Title>
        <Typography.Paragraph>
          上传签字与印章模板后，系统会在货单比对阶段自动调用这些模板。
        </Typography.Paragraph>
      </Card>

      <Card title="上传新模板">
        <Space size={12} wrap>
          <Segmented<DetectionType>
            options={[
              { label: "签字模板", value: "signature" },
              { label: "印章模板", value: "stamp" },
            ]}
            value={templateType}
            onChange={setTemplateType}
          />
          <Upload {...uploadProps}>
            <Button type="primary" loading={uploadMutation.isPending}>
              上传{templateType === "signature" ? "签字" : "印章"}
            </Button>
          </Upload>
        </Space>
      </Card>

      <Card title="模板列表">
        {!templatesQuery.data?.length && <Empty description="暂无模板" />}
        <div className="template-grid">
          {(templatesQuery.data ?? []).map((template) => (
            <Card
              key={template.id}
              size="small"
              cover={
                // eslint-disable-next-line @next/next/no-img-element
                <img src={template.image_url} alt="template" className="template-image" />
              }
              actions={[
                <Popconfirm
                  key={`delete-${template.id}`}
                  title="确认删除该模板吗？"
                  onConfirm={() => deleteMutation.mutate(template.id)}
                >
                  <Button type="link" danger loading={deleteMutation.isPending}>
                    删除
                  </Button>
                </Popconfirm>,
              ]}
            >
              <Typography.Text strong>
                {template.type === "signature" ? "签字模板" : "印章模板"}
              </Typography.Text>
              <br />
              <Typography.Text type="secondary">
                {new Date(template.created_at).toLocaleString()}
              </Typography.Text>
            </Card>
          ))}
        </div>
      </Card>
    </Space>
  );
}
