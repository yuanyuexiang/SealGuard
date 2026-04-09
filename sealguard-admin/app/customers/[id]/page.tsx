"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  Empty,
  Popconfirm,
  Segmented,
  Space,
  Tag,
  Typography,
  Upload,
  message,
} from "antd";
import type { UploadProps } from "antd";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { deleteTemplate, detectImage, getCustomers, getTemplates, uploadTemplate } from "@/services/mockApi";
import type { DetectionType } from "@/types/domain";

type DetectedTemplateCandidate = {
  id: number;
  type: DetectionType;
  confidence: number;
  bbox: [number, number, number, number];
  file: Blob;
  previewUrl: string;
};

const MIN_DETECT_CONFIDENCE = 0.2;
const MAX_TEMPLATE_AREA_RATIO = 0.45;
const MIN_TEMPLATE_SIDE = 20;

function isValidDetectBox(
  bbox: [number, number, number, number],
  imageWidth: number,
  imageHeight: number,
): boolean {
  const [x, y, w, h] = bbox;
  if (w < MIN_TEMPLATE_SIDE || h < MIN_TEMPLATE_SIDE) {
    return false;
  }

  const imageArea = imageWidth * imageHeight;
  const areaRatio = imageArea > 0 ? (w * h) / imageArea : 1;
  if (areaRatio > MAX_TEMPLATE_AREA_RATIO) {
    return false;
  }

  const outOfBounds = x < 0 || y < 0 || x + w > imageWidth + 1 || y + h > imageHeight + 1;
  return !outOfBounds;
}

function getFriendlyErrorMessage(error: Error, actionName: string): string {
  const text = (error.message || "").toLowerCase();

  if (text.includes("failed to fetch") || text.includes("networkerror") || text.includes("network error")) {
    return `${actionName}失败：无法连接后端服务，请确认 API 服务已启动。`;
  }
  if (text.includes("not found")) {
    return `${actionName}失败：目标不存在，列表可能已过期，请刷新后重试。`;
  }

  return `${actionName}失败：${error.message || "请稍后重试"}`;
}

export default function CustomerDetailPage() {
  const params = useParams<{ id: string }>();
  const customerId = Number(params.id);
  const queryClient = useQueryClient();
  const [templateType, setTemplateType] = useState<DetectionType>("signature");
  const [deletingTemplateId, setDeletingTemplateId] = useState<number | null>(null);
  const [detectedCandidates, setDetectedCandidates] = useState<DetectedTemplateCandidate[]>([]);
  const [sourcePreviewUrl, setSourcePreviewUrl] = useState<string | null>(null);
  const [sourceImageSize, setSourceImageSize] = useState<{ width: number; height: number } | null>(null);
  const [savingCandidateId, setSavingCandidateId] = useState<number | "all" | null>(null);

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
    onError: (error: Error) => {
      message.error(getFriendlyErrorMessage(error, "上传模板"));
    },
  });

  const detectMutation = useMutation({
    mutationFn: ({ file, fileName }: { file: Blob; fileName: string }) => detectImage(file, fileName),
    onError: (error: Error) => {
      message.error(getFriendlyErrorMessage(error, "智能检测"));
    },
  });

  useEffect(() => {
    return () => {
      if (sourcePreviewUrl) {
        URL.revokeObjectURL(sourcePreviewUrl);
      }
      for (const candidate of detectedCandidates) {
        URL.revokeObjectURL(candidate.previewUrl);
      }
    };
  }, [detectedCandidates, sourcePreviewUrl]);

  const deleteMutation = useMutation({
    mutationFn: async (templateId: number) => {
      setDeletingTemplateId(templateId);
      await deleteTemplate(templateId);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["templates", customerId] });
      message.success("模板已删除");
    },
    onError: (error: Error) => {
      message.error(getFriendlyErrorMessage(error, "删除模板"));
    },
    onSettled: () => {
      setDeletingTemplateId(null);
    },
  });

  const customer = useMemo(
    () => customersQuery.data?.find((item) => item.id === customerId),
    [customersQuery.data, customerId],
  );

  const releaseDetectedCandidates = () => {
    for (const candidate of detectedCandidates) {
      URL.revokeObjectURL(candidate.previewUrl);
    }
    setDetectedCandidates([]);
  };

  const updateCandidateType = (candidateId: number, nextType: DetectionType) => {
    setDetectedCandidates((prev) =>
      prev.map((item) => (item.id === candidateId ? { ...item, type: nextType } : item)),
    );
  };

  const cropToBlob = async (
    imageBlob: Blob,
    bbox: [number, number, number, number],
  ): Promise<Blob> => {
    const bitmap = await createImageBitmap(imageBlob);
    try {
      const [x, y, w, h] = bbox;
      const sx = Math.max(0, Math.floor(x));
      const sy = Math.max(0, Math.floor(y));
      const sw = Math.max(1, Math.min(bitmap.width - sx, Math.ceil(w)));
      const sh = Math.max(1, Math.min(bitmap.height - sy, Math.ceil(h)));

      const canvas = document.createElement("canvas");
      canvas.width = sw;
      canvas.height = sh;
      const context = canvas.getContext("2d");
      if (!context) {
        throw new Error("无法创建图像画布");
      }

      context.drawImage(bitmap, sx, sy, sw, sh, 0, 0, sw, sh);

      return await new Promise<Blob>((resolve, reject) => {
        canvas.toBlob((blob) => {
          if (!blob) {
            reject(new Error("模板裁剪失败"));
            return;
          }
          resolve(blob);
        }, "image/jpeg", 0.95);
      });
    } finally {
      bitmap.close();
    }
  };

  const detectUploadProps: UploadProps = {
    multiple: false,
    showUploadList: false,
    customRequest: async (options) => {
      if (detectMutation.isPending || uploadMutation.isPending || deleteMutation.isPending || savingCandidateId) {
        options.onError?.(new Error("busy"));
        return;
      }

      try {
        if (typeof options.file === "string") {
          throw new Error("Invalid upload file");
        }

        const fileName =
          "name" in options.file ? options.file.name : `template-source-${Date.now()}.jpg`;
        const candidate =
          "originFileObj" in options.file && options.file.originFileObj
            ? options.file.originFileObj
            : options.file;
        if (!(candidate instanceof Blob)) {
          throw new Error("Invalid upload payload");
        }

        const sourceFile: Blob = candidate;
        const detectResult = await detectMutation.mutateAsync({ file: sourceFile, fileName });

        const imageArea = detectResult.image_width * detectResult.image_height;
        const rawDetections = detectResult.detections.filter(
          (item) => item.type === "signature" || item.type === "stamp",
        );

        const filteredByConfidence = rawDetections.filter(
          (item) => item.confidence >= MIN_DETECT_CONFIDENCE,
        );

        const filteredDetections = filteredByConfidence.filter((item) => {
          const [x, y, w, h] = item.bbox;
          if (w < MIN_TEMPLATE_SIDE || h < MIN_TEMPLATE_SIDE) {
            return false;
          }

          const areaRatio = imageArea > 0 ? (w * h) / imageArea : 1;
          if (areaRatio > MAX_TEMPLATE_AREA_RATIO) {
            return false;
          }

          const outOfBounds =
            x < 0 ||
            y < 0 ||
            x + w > detectResult.image_width + 1 ||
            y + h > detectResult.image_height + 1;
          if (outOfBounds) {
            return false;
          }

          return true;
        });

        if (!filteredDetections.length) {
          releaseDetectedCandidates();
          const rejectedCount = rawDetections.length - filteredDetections.length;
          if (rawDetections.length > 0 && rejectedCount > 0) {
            message.warning("检测到的候选均不符合模板条件（可能是整页误检），请更换图片或手动上传模板。");
          } else {
            message.warning("未检测到签字/印章区域，请更换图片或手动上传模板。");
          }
          options.onSuccess?.({}, options.file);
          return;
        }

        if (sourcePreviewUrl) {
          URL.revokeObjectURL(sourcePreviewUrl);
        }
        setSourcePreviewUrl(URL.createObjectURL(sourceFile));
        setSourceImageSize(null);

        releaseDetectedCandidates();
        const nextCandidates: DetectedTemplateCandidate[] = [];
        for (const item of filteredDetections) {
          const cropped = await cropToBlob(sourceFile, item.bbox);
          nextCandidates.push({
            id: item.id,
            type: item.type as DetectionType,
            confidence: item.confidence,
            bbox: item.bbox,
            file: cropped,
            previewUrl: URL.createObjectURL(cropped),
          });
        }

        setDetectedCandidates(nextCandidates);
        const rejectedCount = rawDetections.length - filteredDetections.length;
        if (rejectedCount > 0) {
          message.success(`已检测到 ${nextCandidates.length} 个可用模板候选，已自动过滤 ${rejectedCount} 个异常候选`);
        } else {
          message.success(`已检测到 ${nextCandidates.length} 个可用模板候选`);
        }
        options.onSuccess?.({}, options.file);
      } catch (error) {
        if (error instanceof Error) {
          options.onError?.(error);
        } else {
          options.onError?.(new Error("detect failed"));
        }
      }
    },
  };

  const uploadProps: UploadProps = {
    multiple: false,
    showUploadList: false,
    customRequest: async (options) => {
      if (uploadMutation.isPending || deleteMutation.isPending || detectMutation.isPending) {
        options.onError?.(new Error("busy"));
        return;
      }

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

        const originalFile: Blob = candidate;
        let uploadFile: Blob = originalFile;

        try {
          const detectResult = await detectMutation.mutateAsync({ file: originalFile, fileName });
          const matchedDetections = detectResult.detections
            .filter((item) => item.type === templateType)
            .filter((item) => item.confidence >= MIN_DETECT_CONFIDENCE)
            .filter((item) => isValidDetectBox(item.bbox, detectResult.image_width, detectResult.image_height))
            .sort((a, b) => b.confidence - a.confidence);

          if (matchedDetections.length > 0) {
            uploadFile = await cropToBlob(originalFile, matchedDetections[0].bbox);
            message.success(`已自动提取${templateType === "signature" ? "签字" : "印章"}区域后上传`);
          } else {
            message.warning(`未检测到可用${templateType === "signature" ? "签字" : "印章"}候选，已按原图上传`);
          }
        } catch {
          message.warning("自动提取失败，已按原图上传");
        }

        await uploadMutation.mutateAsync({ file: uploadFile, fileName });
        options.onSuccess?.({}, options.file);
      } catch (error) {
        if (error instanceof Error) {
          options.onError?.(error);
        } else {
          options.onError?.(new Error("upload failed"));
        }
      }
    },
  };

  const saveDetectedTemplate = async (candidate: DetectedTemplateCandidate) => {
    if (savingCandidateId) {
      return;
    }
    setSavingCandidateId(candidate.id);
    try {
      await uploadTemplate({
        customerIdValue: customerId,
        type: candidate.type,
        file: candidate.file,
        fileName: `${candidate.type}-${Date.now()}.jpg`,
      });
      await queryClient.invalidateQueries({ queryKey: ["templates", customerId] });

      setDetectedCandidates((prev) => {
        const target = prev.find((item) => item.id === candidate.id);
        if (target) {
          URL.revokeObjectURL(target.previewUrl);
        }
        return prev.filter((item) => item.id !== candidate.id);
      });
      message.success("已保存为模板");
    } catch (error) {
      if (error instanceof Error) {
        message.error(getFriendlyErrorMessage(error, "保存模板"));
      } else {
        message.error("保存模板失败，请稍后重试。");
      }
    } finally {
      setSavingCandidateId(null);
    }
  };

  const saveAllDetectedTemplates = async () => {
    if (!detectedCandidates.length || savingCandidateId) {
      return;
    }

    setSavingCandidateId("all");
    let successCount = 0;

    try {
      for (const candidate of [...detectedCandidates]) {
        await uploadTemplate({
          customerIdValue: customerId,
          type: candidate.type,
          file: candidate.file,
          fileName: `${candidate.type}-${Date.now()}-${candidate.id}.jpg`,
        });
        successCount += 1;
      }

      await queryClient.invalidateQueries({ queryKey: ["templates", customerId] });
      releaseDetectedCandidates();
      message.success(`批量保存完成：成功 ${successCount} 个模板`);
    } catch (error) {
      if (error instanceof Error) {
        message.error(getFriendlyErrorMessage(error, "批量保存模板"));
      } else {
        message.error("批量保存失败，请稍后重试。");
      }
    } finally {
      setSavingCandidateId(null);
    }
  };

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Card className="hero-card">
        <Typography.Title level={3}>{customer?.name ?? "客户详情"}</Typography.Title>
        <Typography.Paragraph>
          上传签字与印章模板后，系统会在货单比对阶段自动调用这些模板。
        </Typography.Paragraph>
      </Card>

      <Card title="上传新模板（自动提取）">
        <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
          上传整张单据时，会自动检测并提取当前类型（签字/印章）的最佳候选区域后保存。
        </Typography.Paragraph>
        <Space size={12} wrap>
          <Segmented<DetectionType>
            options={[
              { label: "签字模板", value: "signature" },
              { label: "印章模板", value: "stamp" },
            ]}
            value={templateType}
            onChange={setTemplateType}
            disabled={uploadMutation.isPending || deleteMutation.isPending || detectMutation.isPending}
          />
          <Upload {...uploadProps}>
            <Button
              type="primary"
              loading={uploadMutation.isPending}
              disabled={uploadMutation.isPending || deleteMutation.isPending || detectMutation.isPending}
            >
              上传并提取{templateType === "signature" ? "签字" : "印章"}
            </Button>
          </Upload>
        </Space>
      </Card>

      <Card title="智能检测上传模板（推荐）">
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Upload.Dragger
            {...detectUploadProps}
            accept="image/*"
            disabled={
              detectMutation.isPending || uploadMutation.isPending || deleteMutation.isPending || !!savingCandidateId
            }
          >
            <p>上传一张包含签字/印章的图片，系统会自动检测并裁剪出模板候选。</p>
            <Button type="primary" loading={detectMutation.isPending}>
              开始智能检测
            </Button>
          </Upload.Dragger>

          {sourcePreviewUrl && (
            <Space direction="vertical" size={8} style={{ width: "100%" }}>
              <Typography.Text type="secondary">
                已载入源图，检测候选数：{detectedCandidates.length}
              </Typography.Text>
              <div className="source-preview-wrap">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={sourcePreviewUrl}
                  alt="source-preview"
                  className="source-preview-image"
                  onLoad={(event) => {
                    const target = event.currentTarget;
                    setSourceImageSize({ width: target.naturalWidth, height: target.naturalHeight });
                  }}
                />
                {sourceImageSize &&
                  detectedCandidates.map((candidate) => {
                    const [x, y, w, h] = candidate.bbox;
                    const left = (x / sourceImageSize.width) * 100;
                    const top = (y / sourceImageSize.height) * 100;
                    const width = (w / sourceImageSize.width) * 100;
                    const height = (h / sourceImageSize.height) * 100;
                    return (
                      <div
                        key={`overlay-${candidate.id}`}
                        className={`source-detect-box source-detect-box-${candidate.type}`}
                        style={{
                          left: `${left}%`,
                          top: `${top}%`,
                          width: `${width}%`,
                          height: `${height}%`,
                        }}
                      >
                        <span className="source-detect-label">
                          {candidate.type === "signature" ? "签字" : "印章"} {candidate.confidence.toFixed(2)}
                        </span>
                      </div>
                    );
                  })}
              </div>
            </Space>
          )}

          {!!detectedCandidates.length && (
            <Space>
              <Button
                type="primary"
                onClick={saveAllDetectedTemplates}
                loading={savingCandidateId === "all"}
                disabled={!!savingCandidateId}
              >
                一键保存全部候选
              </Button>
              <Button
                onClick={() => {
                  releaseDetectedCandidates();
                  if (sourcePreviewUrl) {
                    URL.revokeObjectURL(sourcePreviewUrl);
                    setSourcePreviewUrl(null);
                  }
                }}
                disabled={!!savingCandidateId}
              >
                清空候选
              </Button>
            </Space>
          )}

          {!!detectedCandidates.length && (
            <div className="template-grid">
              {detectedCandidates.map((candidate) => (
                <Card
                  key={`candidate-${candidate.id}`}
                  size="small"
                  cover={
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={candidate.previewUrl} alt="detected-template" className="template-image" />
                  }
                  actions={[
                    <Button
                      key={`save-${candidate.id}`}
                      type="link"
                      onClick={() => saveDetectedTemplate(candidate)}
                      loading={savingCandidateId === candidate.id}
                      disabled={!!savingCandidateId}
                    >
                      保存为模板
                    </Button>,
                  ]}
                >
                  <Space direction="vertical" size={8} style={{ width: "100%" }}>
                    <Typography.Text strong>
                      {candidate.type === "signature" ? "签字候选" : "印章候选"}
                    </Typography.Text>
                    <Segmented<DetectionType>
                      options={[
                        { label: "签字", value: "signature" },
                        { label: "印章", value: "stamp" },
                      ]}
                      value={candidate.type}
                      onChange={(value) => updateCandidateType(candidate.id, value)}
                      disabled={!!savingCandidateId}
                    />
                  </Space>
                  <br />
                  <Space size={8}>
                    <Typography.Text type="secondary">
                      置信度：{candidate.confidence.toFixed(3)}
                    </Typography.Text>
                    <Tag color={candidate.type === "signature" ? "red" : "gold"}>
                      {candidate.type === "signature" ? "签字" : "印章"}
                    </Tag>
                  </Space>
                </Card>
              ))}
            </div>
          )}
        </Space>
      </Card>

      <Card title="模板列表">
        {templatesQuery.isError && (
          <Alert
            type="warning"
            showIcon
            message="模板列表加载失败"
            description="无法连接后端服务或请求异常，请检查后端状态后重试。"
            style={{ marginBottom: 12 }}
          />
        )}
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
                  disabled={deleteMutation.isPending || uploadMutation.isPending}
                  onConfirm={() => deleteMutation.mutate(template.id)}
                >
                  <Button
                    type="link"
                    danger
                    loading={deleteMutation.isPending && deletingTemplateId === template.id}
                    disabled={deleteMutation.isPending || uploadMutation.isPending}
                  >
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
