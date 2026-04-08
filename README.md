---

# SealGuard

SealGuard 是一套基于 AI 的送货单签字与印章识别与比对系统，支持自动检测、相似度比对以及人工审核，适用于物流、供应链等单据核验场景。

---

# 一、项目简介

SealGuard 通过计算机视觉与深度学习技术，实现：

* 自动识别送货单中的签字和盖章
* 与客户预留模板进行相似度比对
* 输出可信分值与判定结果
* 支持人工审核与结果修正
* 提供完整的历史记录与审计能力

---

# 二、核心功能

## 1. 客户与模板管理

* 客户信息管理
* 签字模板登记
* 印章模板登记
* 模板图片管理（上传/删除）

## 2. 货单识别与比对

* 上传送货单图片
* 自动检测签字/印章（YOLO）
* 自动裁剪并提取特征
* 与模板库进行相似度比对（Siamese）

## 3. 审核中心（关键功能）

* AI结果展示（检测框 + 分值）
* 左右对比图（检测 vs 模板）
* 人工判定（通过 / 不通过 / 可疑）

## 4. 历史记录

* 查询检测任务
* 支持筛选（时间 / 客户 / 结果）
* 审计日志（记录人工操作）

---

# 三、系统架构（简化版）

```
Frontend (React Admin)
        ↓
FastAPI Backend（同步处理）
        ↓
AI模块（YOLO + Siamese）
        ↓
PostgreSQL + MinIO
```

说明：

* 不使用消息队列
* 上传后由后端同步调用 AI 推理
* 适用于第一版快速交付

---

# 四、技术栈

## 前端

* React / Next.js
* Ant Design
* react-konva（检测框展示）

## 后端

* FastAPI
* SQLAlchemy
* Pydantic

## AI

* PyTorch
* YOLO（目标检测）
* Siamese Network（相似度比对）

## 数据

* PostgreSQL + pgvector（向量检索）
* MinIO（图片存储）

---

# 五、核心流程

```
1. 上传送货单
2. YOLO检测签字/印章
3. 裁剪目标区域
4. 图像预处理
5. Siamese模型生成特征向量
6. 与模板库计算相似度
7. 返回结果
8. 人工审核（可选）
```

---

# 六、相似度判定规则

| 分值范围       | 判定  |
| ---------- | --- |
| ≥ 0.85     | 一致  |
| 0.6 ~ 0.85 | 可疑  |
| < 0.6      | 不一致 |

---

# 七、项目结构

```
SealGuard/
├─ README.md
├─ .env.example
├─ .gitignore
├─ sealguard-admin/    # 前端（React/Next）
├─ sealguard-api/      # 后端（FastAPI）
│  ├─ app/
│  │  ├─ api/
│  │  ├─ models/
│  │  ├─ schemas/
│  │  ├─ services/
│  │  └─ main.py
│  └─ requirements.txt
├─ sealguard-ai/       # 模型代码
└─ sealguard-infra/    # 部署配置（docker-compose）
```

---

# 八、快速启动

## 1. 克隆项目

```
git clone <repo_url>
cd sealguard
```

---

## 2. 启动依赖服务

```
cd sealguard-infra
docker-compose up -d postgres minio
```

---

## 3. 启动后端

```
cd sealguard-api
uv run uvicorn app.main:app --reload
```

---

## 4. 启动前端

```
cd sealguard-admin
npm install
npm run dev
```

---

# 九、API 示例

## 上传货单

```
POST /api/upload
```

返回：

```json
{
  "task_id": "123"
}
```

---

## 查询结果

```
GET /api/result/{task_id}
```

---

## 人工审核

```
POST /api/review
```

---

# 十、性能指标（第一版建议）

* 单张处理时间 ≤ 3 秒
* 检测召回率 ≥ 90%
* 比对准确率 ≥ 85%

---

# 十一、部署说明

使用 Docker：

```
docker-compose up -d
```

包含服务：

* api
* postgres
* minio

---

# 十二、注意事项

* 第一版为同步处理，请控制并发
* 签名具有随机性，需多模板支持
* 必须保留人工审核机制

---

# 十三、未来优化方向

* 引入异步任务队列（提升并发）
* 模型优化（提升准确率）
* 多租户支持（SaaS化）

---

# 十四、License

内部项目 / 商业使用请根据实际情况定义 License

---

