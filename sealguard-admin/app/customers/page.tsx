"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Form, Input, List, Modal, Space, Typography, message } from "antd";
import Link from "next/link";
import { useMemo, useState } from "react";

import { createCustomer, deleteCustomer, getCustomerStats, getCustomers, updateCustomer } from "@/services/mockApi";
import type { Customer } from "@/types/domain";

function isNetworkError(error: Error): boolean {
  const text = (error.message || "").toLowerCase();
  return text.includes("failed to fetch") || text.includes("networkerror") || text.includes("network error");
}

function isNotFoundError(error: Error): boolean {
  const text = (error.message || "").toLowerCase();
  return text.includes("not found");
}

function getFriendlyErrorMessage(error: Error, actionName: string): string {
  if (isNetworkError(error)) {
    return `${actionName}失败：无法连接后端服务，请确认 API 服务已启动。`;
  }

  const text = (error.message || "").toLowerCase();
  if (text.includes("already exists")) {
    return `${actionName}失败：客户名称已存在，请更换名称。`;
  }

  if (isNotFoundError(error)) {
    return `${actionName}失败：客户不存在，列表可能已过期，请刷新后重试。`;
  }

  return `${actionName}失败：${error.message || "请稍后重试"}`;
}

export default function CustomersPage() {
  const queryClient = useQueryClient();
  const [form] = Form.useForm<{ name: string }>();
  const [searchKeyword, setSearchKeyword] = useState("");
  const [editingCustomer, setEditingCustomer] = useState<{ id: number; name: string } | null>(null);
  const [deletingCustomer, setDeletingCustomer] = useState<Customer | null>(null);
  const [deletingCustomerId, setDeletingCustomerId] = useState<number | null>(null);
  const [editForm] = Form.useForm<{ name: string }>();

  const { data, isLoading } = useQuery({
    queryKey: ["customers"],
    queryFn: getCustomers,
  });

  const createMutation = useMutation({
    mutationFn: (name: string) => createCustomer(name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["customers"] });
      form.resetFields();
      message.success("客户新增成功");
    },
    onError: (error: Error) => {
      message.error(getFriendlyErrorMessage(error, "新增客户"));
    },
  });

  const updateMutation = useMutation({
    mutationFn: (params: { id: number; name: string }) => updateCustomer(params.id, params.name),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["customers"] });
      setEditingCustomer(null);
      editForm.resetFields();
      message.success("客户名称已更新");
    },
    onError: (error: Error) => {
      message.error(getFriendlyErrorMessage(error, "更新客户"));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (customerId: number) => {
      setDeletingCustomerId(customerId);
      await deleteCustomer(customerId);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["customers"] });
      setDeletingCustomer(null);
      setDeletingCustomerId(null);
      message.success("客户已删除");
    },
    onError: (error: Error) => {
      setDeletingCustomerId(null);
      if (isNotFoundError(error)) {
        queryClient.invalidateQueries({ queryKey: ["customers"] });
        setDeletingCustomer(null);
        message.warning("客户已不存在，列表已自动刷新。");
        return;
      }
      message.error(getFriendlyErrorMessage(error, "删除客户"));
    },
    onSettled: () => {
      setDeletingCustomerId(null);
    },
  });

  const filteredCustomers = useMemo(() => {
    const source = data ?? [];
    const keyword = searchKeyword.trim().toLowerCase();
    if (!keyword) {
      return source;
    }
    return source.filter((item) => item.name.toLowerCase().includes(keyword));
  }, [data, searchKeyword]);

  const openEditModal = (customer: { id: number; name: string }) => {
    setEditingCustomer(customer);
    editForm.setFieldsValue({ name: customer.name });
  };

  const customerStatsQuery = useQuery({
    queryKey: ["customer-stats", deletingCustomer?.id],
    queryFn: () => getCustomerStats(deletingCustomer!.id),
    enabled: !!deletingCustomer,
  });

  const customerStatsError = customerStatsQuery.error instanceof Error ? customerStatsQuery.error : null;
  const statsErrorIsNetwork = customerStatsError ? isNetworkError(customerStatsError) : false;
  const statsErrorIsNotFound = customerStatsError ? isNotFoundError(customerStatsError) : false;

  const closeEditModal = () => {
    if (updateMutation.isPending) {
      return;
    }
    setEditingCustomer(null);
    editForm.resetFields();
  };

  const submitEdit = async () => {
    const values = await editForm.validateFields();
    if (!editingCustomer) {
      return;
    }
    await updateMutation.mutateAsync({ id: editingCustomer.id, name: values.name });
  };

  const confirmDelete = async () => {
    if (!deletingCustomer) {
      return;
    }
    if (deleteMutation.isPending) {
      return;
    }
    await deleteMutation.mutateAsync(deletingCustomer.id);
  };

  const cancelDelete = () => {
    if (deleteMutation.isPending) {
      return;
    }
    setDeletingCustomer(null);
    setDeletingCustomerId(null);
  };

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Card className="hero-card">
        <Typography.Title level={3}>客户与签章模板管理</Typography.Title>
        <Typography.Paragraph>
          维护客户与模板是比对准确率的基础。请先完成客户登记，再上传签字与印章模板。
        </Typography.Paragraph>
      </Card>

      <Card title="新增客户">
        <Form
          form={form}
          layout="inline"
          onFinish={(values) => createMutation.mutate(values.name)}
        >
          <Form.Item
            name="name"
            rules={[{ required: true, message: "请输入客户名称" }]}
            style={{ minWidth: 320 }}
          >
            <Input placeholder="例如：可口可乐华北配送中心" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={createMutation.isPending}>
              新增客户
            </Button>
          </Form.Item>
        </Form>
      </Card>

      <Card title="客户列表">
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Input.Search
            allowClear
            placeholder="按客户名称搜索"
            value={searchKeyword}
            onChange={(e) => setSearchKeyword(e.target.value)}
          />

        <List
          loading={isLoading}
          dataSource={filteredCustomers}
          rowKey="id"
          renderItem={(item) => (
            <List.Item
              actions={[
                <Link href={`/customers/${item.id}`} key={`view-${item.id}`}>
                  查看模板
                </Link>,
                <Button type="link" key={`edit-${item.id}`} onClick={() => openEditModal(item)}>
                  编辑
                </Button>,
                  <Button
                    type="link"
                    danger
                    key={`delete-${item.id}`}
                    loading={deleteMutation.isPending && deletingCustomerId === item.id}
                    disabled={deleteMutation.isPending || updateMutation.isPending}
                    onClick={() => setDeletingCustomer(item)}
                  >
                    删除
                  </Button>,
              ]}
            >
                <List.Item.Meta
                  title={item.name}
                  description={`客户ID: ${item.id} | 模板总数: ${item.template_total ?? 0}（签字 ${item.signature_templates ?? 0} / 印章 ${item.stamp_templates ?? 0}）`}
                />
            </List.Item>
          )}
        />
        </Space>
      </Card>

      <Modal
        title="编辑客户"
        open={!!editingCustomer}
        onCancel={closeEditModal}
        onOk={submitEdit}
        okText="保存"
        cancelText="取消"
        confirmLoading={updateMutation.isPending}
      >
        <Form form={editForm} layout="vertical">
          <Form.Item
            name="name"
            label="客户名称"
            rules={[{ required: true, message: "请输入客户名称" }]}
          >
            <Input placeholder="请输入客户名称" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="确认删除客户"
        open={!!deletingCustomer}
        onCancel={cancelDelete}
        onOk={confirmDelete}
        okText="确认删除"
        okButtonProps={{ danger: true }}
        cancelText="取消"
        confirmLoading={deleteMutation.isPending}
      >
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Typography.Text>
            将删除客户“{deletingCustomer?.name ?? ""}”及其下所有模板，此操作不可恢复。
          </Typography.Text>
          {customerStatsQuery.isLoading && <Typography.Text type="secondary">正在加载影响统计...</Typography.Text>}
          {customerStatsQuery.isError && (
            <Alert
              type="warning"
              showIcon
              message="无法加载影响统计"
              description={
                statsErrorIsNetwork
                  ? "后端服务暂不可用，当前无法获取统计。建议先检查后端状态。"
                  : statsErrorIsNotFound
                    ? "客户可能已被删除。你仍可点击“确认删除”以刷新列表状态。"
                    : "请求异常。你仍可继续删除，但建议先刷新后重试。"
              }
            />
          )}
          {customerStatsQuery.data && (
            <Alert
              type="info"
              showIcon
              message="删除影响"
              description={`模板总数 ${customerStatsQuery.data.template_total}（签字 ${customerStatsQuery.data.signature_templates} / 印章 ${customerStatsQuery.data.stamp_templates}）`}
            />
          )}
        </Space>
      </Modal>
    </Space>
  );
}
