# SealGuard 前端开发指南（标准版）

本文档用于统一 SealGuard 前端实现规范，适用于产品、设计、前端、后端与测试协作。

## 1. 文档目标

- 明确页面范围与交互边界
- 统一接口契约与数据结构
- 固化可口可乐品牌视觉规范，避免设计偏移
- 提供可直接用于代码生成与开发执行的标准输入

## 2. 技术选型

```text
框架：React（推荐 Next.js App Router）
UI：Ant Design（可按需结合 shadcn/ui）
状态管理：React Query + Zustand
图像标注：react-konva
```

## 3. 品牌与视觉规范（可口可乐风格，硬约束）

### 3.1 视觉基调

- 高对比、强识别、动感曲线
- 避免“通用后台模板感”
- 关键按钮与关键状态必须高可见

### 3.2 色彩建议

```text
主色：品牌红（主行动）
中性色：白、黑、深灰（信息承载）
状态色：
- 通过：绿色
- 不通过：红色
- 可疑：橙色
```

### 3.3 页面与组件要求

- 背景使用渐变、曲线或轻肌理，不使用单一纯色平铺
- 标题与关键数字强调视觉冲击，正文保证可读性
- 按钮、标签、卡片有明确层级和主次关系
- 桌面端与移动端保持统一品牌观感

## 4. 功能范围

前端覆盖 4 个业务模块：

1. 客户与模板管理
2. 货单上传与自动比对
3. 人工审核
4. 历史记录查询

## 5. 路由规划（Next.js App Router）

```text
/app
  /customers
  /customers/[id]
  /upload
  /review
  /history
```

## 6. 数据模型（前端）

```ts
type Customer = {
  id: number;
  name: string;
};

type Template = {
  id: number;
  type: "signature" | "stamp";
  image_url: string;
  created_at: string;
};

type Detection = {
  id: number;
  type: "signature" | "stamp";
  bbox: [number, number, number, number];
  score: number;
  result: "true" | "false" | "suspicious";
};
```

## 7. 页面规格

### 7.1 客户与模板管理页（/customers, /customers/[id]）

功能目标：

- 新增客户
- 上传签字/印章模板
- 管理模板（查看、删除）

页面结构：

```text
客户列表 -> 客户详情
客户详情：基本信息 / 签字模板 / 印章模板 / 上传入口
```

上传说明：

- 前端只负责文件上传和结果展示
- 后端负责检测、裁剪、embedding、入库

### 7.2 货单上传与自动比对页（/upload）

功能目标：

- 上传货单
- 展示任务状态
- 展示检测框与比对结果

关键交互：

- 上传成功后拿到 task_id
- 轮询结果接口直至 status=done
- 使用 react-konva 绘制检测框

### 7.3 人工审核页（/review）

功能目标：

- 左侧检测图（带框）
- 右侧模板图
- 底部审核动作（通过 / 不通过 / 可疑）

交互要求：

- 显示相似度分值
- 审核动作需即时反馈成功/失败
- 建议支持快捷键提升审核效率

### 7.4 历史记录页（/history）

功能目标：

- 查询历史货单
- 查看检测结果与审核记录

表格字段建议：

- 货单 ID
- 创建时间
- 状态
- 操作（查看详情）

## 8. API 契约

### 8.1 客户

```text
GET  /api/customers
POST /api/customers
```

### 8.2 模板

```text
POST   /api/templates/upload
GET    /api/templates?customer_id={id}
DELETE /api/templates/{id}
```

### 8.3 货单

```text
POST /api/upload
GET  /api/result/{task_id}
```

结果示例：

```json
{
  "status": "done",
  "detections": [
    {
      "id": 1,
      "type": "signature",
      "bbox": [100, 120, 220, 80],
      "score": 0.92,
      "result": "true"
    }
  ]
}
```

### 8.4 审核

```text
POST /api/review
```

请求体：

```json
{
  "detect_id": 123,
  "result": "suspicious"
}
```

## 9. 体验优化清单（建议）

1. 拖拽上传
2. 图片缩放与平移
3. 检测框 hover 显示分值
4. 审核快捷键

## 10. 验收标准（MVP）

- 能完成客户创建与模板上传
- 能上传货单并完成结果轮询
- 能正确渲染检测框和比对状态
- 能提交人工审核结果并持久化
- 能在历史页查询并查看详情
- 主要页面在桌面端和移动端均可用

## 11. AI 代码生成输入模板

```text
请基于 React + Ant Design + Next.js App Router 实现 SealGuard 前端，页面包括：
1) 客户管理（新增客户、上传签字/印章模板、模板卡片展示）
2) 货单上传（上传图片、轮询任务状态、检测框可视化）
3) 审核页面（左右对比图、相似度、通过/不通过/可疑）
4) 历史记录（表格展示、详情查看）

必须遵循可口可乐风格：红白黑主色、高对比、动感曲线背景、强层级按钮。
接口使用 RESTful JSON，按以下路径：
/api/customers, /api/templates/upload, /api/templates, /api/upload, /api/result/{task_id}, /api/review。
```

## 12. 关键结论

前端核心不是“仅展示图片”，而是：

1. 模板管理（数据基础）
2. 检测结果可视化（业务可解释）
3. 人工审核闭环（质量保障）
