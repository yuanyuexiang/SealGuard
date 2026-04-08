"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, Form, Input, List, Space, Typography } from "antd";
import Link from "next/link";

import { createCustomer, getCustomers } from "@/services/mockApi";

export default function CustomersPage() {
  const queryClient = useQueryClient();
  const [form] = Form.useForm<{ name: string }>();

  const { data, isLoading } = useQuery({
    queryKey: ["customers"],
    queryFn: getCustomers,
  });

  const createMutation = useMutation({
    mutationFn: (name: string) => createCustomer(name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["customers"] });
      form.resetFields();
    },
  });

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
        <List
          loading={isLoading}
          dataSource={data ?? []}
          rowKey="id"
          renderItem={(item) => (
            <List.Item
              actions={[
                <Link href={`/customers/${item.id}`} key={`view-${item.id}`}>
                  查看模板
                </Link>,
              ]}
            >
              <List.Item.Meta title={item.name} description={`客户ID: ${item.id}`} />
            </List.Item>
          )}
        />
      </Card>
    </Space>
  );
}
