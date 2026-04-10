# SealGuard

SealGuard 是一套面向物流/供应链场景的送货单签字与印章核验系统，支持检测、相似度比对、人工审核与历史追溯。

## 一、当前实现状态

已完成：

- 前端管理端（客户模板、上传检测、人工审核、历史记录）
- 后端 DDD 分层架构（采用 `app` 目录）
- YOLO 检测链路
- 本地文件存储（无 MinIO）
- 模板 embedding 存储与向量相似度匹配（Siamese 风格适配器）

说明：当前 `Siamese` 已落“embedding + 向量相似度”契约。编码器实现可无缝替换为真实 Siamese 权重推理。

## 二、系统架构

```text
Frontend (Next.js Admin)
        ↓
FastAPI Backend (DDD, synchronous)
        ↓
AI: YOLO detect + embedding matcher
        ↓
PostgreSQL + Local File Storage
```

## 三、项目结构

```text
SealGuard/
├─ README.md
├─ sealguard-admin/
│  ├─ app/
│  ├─ components/
│  ├─ services/
│  └─ ...
├─ sealguard-api/
│  ├─ app/
│  │  ├─ main.py
│  │  ├─ interfaces/
│  │  ├─ application/
│  │  ├─ domain/
│  │  ├─ infrastructure/
│  │  ├─ bootstrap/
│  │  └─ shared/
│  ├─ artifacts/sealvision/
│  ├─ pyproject.toml
│  └─ uv.lock
├─ sealguard-ai/
└─ sealguard-infra/
```

## 四、快速启动

### 1. 启动后端

```bash
cd sealguard-api
uv sync --python 3.12
uv run uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

### 2. 启动前端

```bash
cd sealguard-admin
npm install
npm run dev -- --port 3002
```

前端通过同源代理访问后端：`/backend/*`。

## 五、核心接口

- `GET /api/customers`
- `POST /api/customers`
- `GET /api/templates?customer_id={id}`
- `POST /api/templates/upload`
- `DELETE /api/templates/{template_id}`
- `POST /api/upload`
- `GET /api/result/{task_id}`
- `GET /api/tasks/{task_id}`
- `GET /api/tasks/latest`
- `POST /api/review`
- `GET /api/history`
- `POST /api/detect`

## 六、相似度判定规则

| 分值范围 | 判定 |
| --- | --- |
| ≥ 0.85 | 一致 |
| 0.6 ~ 0.85 | 可疑 |
| < 0.6 | 不一致 |

## 七、注意事项

- 当前为同步处理版本，高并发建议后续接任务队列。
- 本地存储目录默认为 `sealguard-api/runtime`。
- 若历史模板无 embedding，可执行回填脚本：

```bash
cd sealguard-api
uv run python -m app.bootstrap.backfill_template_embeddings
```

## 八、License

内部项目 / 商业使用请根据实际情况定义 License。

