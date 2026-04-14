# RAG_GPTV1.0

基于论文知识库的本地 RAG 实验项目，包含检索、重写、图扩展、证据门控与多服务产品化壳层（Frontend + Gateway + Python Kernel）。

## 文档导航

为实现“职责分离”，README 只保留项目总览与入口索引，具体操作手册独立维护。

- 启动教程手册（推荐先看）：[docs/startup-guide.md](docs/startup-guide.md)
- Nginx 生产反代部署（推荐生产使用）：[docs/nginx-production.md](docs/nginx-production.md)
- 多服务开发说明（端口/架构）：[docs/multi-service-dev.md](docs/multi-service-dev.md)
- 历史完整版 README（已归档）：[docs/legacy-readme-full.md](docs/legacy-readme-full.md)
- Pipeline 工作台与任务进度说明：[docs/pipeline-workbench.md](docs/pipeline-workbench.md)
- PDF Marker 解析与灰度/回滚说明：[docs/marker-ingest-ops.md](docs/marker-ingest-ops.md)
- Qdrant 向量存储部署指南：[docs/qdrant-deployment.md](docs/qdrant-deployment.md)

## 项目结构

- `app/`: Python 核心能力（ingest / retrieve / rewrite / qa / kernel_api）
  - `app/vector_store/`: 向量存储抽象层（内存/Qdrant 后端）
- `frontend/`: Next.js 聊天前端
- `gateway/`: Node 网关（WebSocket 协议编排）
- `configs/`: 配置文件（默认 `default.yaml`）
- `data/`: 语料、索引与中间产物
- `runs/`: 每轮运行产物（trace/report）
- `tests/`: Python 回归测试
- `docs/`: 项目文档
- `openspec/`: 变更与规范产出物

## 当前能力概览

- 本地论文 RAG 全链路：入库 -> 清洗 -> 索引 -> 检索 -> 回答
- `Local / Web / Hybrid` 三模式
- 流式输出（FastAPI SSE + Gateway WebSocket）
- 统一引用结构与编号映射
- GraphRAG 子图可视化与引用联动
- 多轮会话与开发者审查视图
- **向量存储后端**：支持内存存储（默认）和 Qdrant 向量数据库

## Web 联网模式说明

- 默认是可运行优先：`WEB_PROVIDER=mock`、`WEB_PROVIDER_STRICT=false`
- 若需“真实联网失败即报错”：
  `WEB_PROVIDER=duckduckgo WEB_PROVIDER_STRICT=true scripts/dev-up.sh`
- 联网状态请查看：`http://127.0.0.1:8080/health/deps`

## 开发原则（简）

- 优先通过文档手册执行启动和联调，不在 README 堆叠长流程。
- 新增操作流程时，优先写入 `docs/` 并在 README 增加入口链接。
- README 保持“短、准、可导航”。

## 生产部署提示

- 生产环境推荐通过单域名 Nginx 暴露服务，不要让浏览器直接访问 `8000` 或 `8080`。
- 在 Cloud Studio 这类平台端口封装环境中，推荐再起一个内部 Nginx 单端口入口，只对外暴露一个应用端口。
- 该单端口入口需要同时代理应用 `/ws` 和 `next dev` 的 `/_next/webpack-hmr`。
- 推荐浏览器只访问：
  - `https://your-domain.com/chat`
  - `https://your-domain.com/pipeline`
  - `https://your-domain.com/settings`
- 对应代理关系：
  - `/` -> frontend
  - `/api/*` -> kernel
  - `/ws` -> gateway
- 可直接复用的模板见 [deploy/nginx/rag-gpt.conf](/home/programer/RAG_GPTV1.0/deploy/nginx/rag-gpt.conf)。
- Cloud Studio 单端口启动可用 [scripts/cloudstudio-up.sh](/home/programer/RAG_GPTV1.0/scripts/cloudstudio-up.sh)。
