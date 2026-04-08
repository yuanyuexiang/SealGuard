"use client";

import {
  AuditOutlined,
  CloudUploadOutlined,
  HistoryOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  TeamOutlined,
} from "@ant-design/icons";
import { Button, Layout, Menu, Typography } from "antd";
import type { MenuProps } from "antd";
import { usePathname, useRouter } from "next/navigation";
import { useMemo } from "react";

import BrandMark from "@/components/BrandMark";
import { useUiStore } from "@/stores/uiStore";

const { Header, Sider, Content } = Layout;

const menuItems: MenuProps["items"] = [
  { key: "/customers", icon: <TeamOutlined />, label: "客户管理" },
  { key: "/upload", icon: <CloudUploadOutlined />, label: "货单上传" },
  { key: "/review", icon: <AuditOutlined />, label: "人工审核" },
  { key: "/history", icon: <HistoryOutlined />, label: "历史记录" },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { collapsed, toggleCollapsed } = useUiStore();

  const selectedKey = useMemo(() => {
    if (pathname.startsWith("/customers")) return "/customers";
    if (pathname.startsWith("/upload")) return "/upload";
    if (pathname.startsWith("/review")) return "/review";
    if (pathname.startsWith("/history")) return "/history";
    return "/customers";
  }, [pathname]);

  return (
    <Layout className="app-shell">
      <Sider
        trigger={null}
        collapsible
        collapsed={collapsed}
        className="app-sider"
        width={264}
      >
        <div className="sider-inner">
          <div className="brand-block">{collapsed ? <BrandMark compact /> : <BrandMark />}</div>
          <Menu
            mode="inline"
            selectedKeys={[selectedKey]}
            items={menuItems}
            onClick={(item) => router.push(item.key)}
            className="brand-menu"
          />
          <div className="sider-footer">
            <span className="sider-pill">模拟环境</span>
            <span className="sider-note">可口可乐核验中台</span>
          </div>
        </div>
      </Sider>
      <Layout>
        <Header className="app-header">
          <Button
            type="text"
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={toggleCollapsed}
            aria-label="toggle menu"
          />
          <div className="header-brand">
            <BrandMark compact />
          </div>
          <Typography.Title level={4} className="page-title">
            送货单智能核验系统
          </Typography.Title>
        </Header>
        <Content className="app-content">{children}</Content>
      </Layout>
    </Layout>
  );
}
