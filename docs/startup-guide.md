# 启动教程手册（Frontend + Gateway + FastAPI Kernel）

本手册只负责“如何启动并体验系统”，与项目设计/算法细节分离。

## 1. 适用场景

- 本地联调三服务：
  - `frontend`（Next.js）
  - `gateway`（Node + WebSocket）
  - `python-kernel`（FastAPI + SSE）
- 体验流式打字机效果、`Local/Web/Hybrid` 模式切换、引用卡片与开发者视图。

## 2. 端口约定

- `3000`：前端 `http://localhost:3000/chat`
- `8080`：网关 `http://127.0.0.1:8080`
- `8000`：Python 内核 `http://127.0.0.1:8000`

## 3. 首次安装依赖

在仓库根目录执行：

```bash
cd frontend && npm install
cd ../gateway && npm install
cd .. && venv/bin/python -m pip install -r requirements.txt
```

说明：`npm audit` 漏洞提示不会阻塞本地启动；不要直接运行 `npm audit fix --force`，避免破坏性升级。`requirements.txt` 已包含可选 `marker-pdf`，安装失败不会阻断 legacy ingest 路径。

## 4. 一键启动（推荐）

```bash
cd /home/programer/RAG_GPTV1.0
scripts/dev-up.sh
```

启动成功后会打印：

- `python-kernel-fastapi pid=... url=http://127.0.0.1:8000`
- `gateway pid=... url=http://127.0.0.1:8080`
- `frontend pid=... url=http://127.0.0.1:3000`

说明：`scripts/dev-up.sh` 会自动为前端注入
`NEXT_PUBLIC_KERNEL_BASE_URL=http://127.0.0.1:8000`（或你覆盖后的 `KERNEL_HOST/KERNEL_PORT`）。
前端管理接口（`/api/admin/*`）路由优先级为：

1. 显式 `NEXT_PUBLIC_KERNEL_BASE_URL`
2. Next rewrites 兜底转发到 Kernel

注意：这里的地址注入是为“本机三服务联调”准备的开发默认值，不适合作为远程服务器部署时给浏览器直接访问的通用配置。

## 4.1 远程部署 / 反向代理说明

如果你把前端部署在远程服务器，并从自己的浏览器访问该页面：

- 不要让浏览器默认连接 `localhost` 或 `127.0.0.1`
- 推荐将前端、`/api/admin/*` 和 `/ws` 统一收口到同一域名/端口
- 若使用 HTTPS，WebSocket 必须对应为 `wss://`

推荐顺序：

1. **同域反向代理（推荐）**
   - 浏览器访问 `https://your-domain/chat`
   - 前端默认请求同域 `/api/admin/*`
   - 前端默认连接同域 `/ws`
   - 反向代理将 `/api/admin/*` 转发到 Kernel，将 `/ws` 转发到 Gateway

2. **显式公网地址覆盖**
   - 当你不使用同域反向代理时，显式设置：
     - `NEXT_PUBLIC_KERNEL_BASE_URL=http(s)://<你的服务地址>:<端口>`
     - `NEXT_PUBLIC_GATEWAY_WS_URL=ws(s)://<你的服务地址>:<端口>/ws`

错误示例：

- 页面由 `http://your-server:3000` 提供，但浏览器去连 `ws://localhost:8080/ws`
- 页面由 `https://your-domain` 提供，但浏览器去连 `ws://...` 而不是 `wss://...`
- 浏览器直接请求 `http://127.0.0.1:8000/api/admin/...`

这些情况都会把请求错误地指向浏览器所在机器，或触发 mixed content / 连接拒绝问题。

如果你要做正式生产部署，优先参考：

- [docs/nginx-production.md](/home/programer/RAG_GPTV1.0/docs/nginx-production.md)

该文档包含：
- 单域 Nginx 配置模板
- `/api/admin/*`、`/api/library/*`、`/api/tasks/*`、`/ws` 的代理规则
- 生产环境推荐的环境变量约定
- 页面、HTTP API、WebSocket 的最小验证步骤

## 5. 健康检查

另开终端：

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/health/deps
```

`/health/deps` 会返回以下关键字段：
- `kernel_ok`
- `web_provider_ok`
- `provider_used`
- `is_mock_fallback`
- `last_web_provider_error`
- `last_fallback_reason`

可用于判断当前是否真实联网，还是回退到了 mock。

## 5.1 Web Provider 默认与严格模式

默认行为（未设置环境变量时）：
- `WEB_PROVIDER=mock`
- `WEB_PROVIDER_STRICT=false`

这意味着默认可以启动并体验 Web/Hybrid 流程，但不是严格的“真实联网保证”。

如果你要强制真实联网（推荐验收时使用）：

```bash
WEB_PROVIDER=duckduckgo WEB_PROVIDER_STRICT=true scripts/dev-up.sh
```

在严格模式下，DuckDuckGo 失败会直接返回错误，不会静默回退 mock。

## 6. 功能体验清单

1. 打开 `http://localhost:3000/chat`
2. 发送问题，确认回答流式输出（打字机效果）
3. 切换 `Local / Web / Hybrid` 模式分别提问
4. 在 `Web / Hybrid` 模式下检查网关事件（Developer 视图）中的 `meta.webProvider`：
   - `providerUsed`
   - `isMockFallback`
   - `fallbackReason`
5. 点击回答中的引用 `[n]`，确认来源卡片联动
6. 切换 `User View / Developer View`，确认 `traceId` 显隐符合预期

## 7. 验证 SSE 流（可选）

```bash
curl -N -X POST http://127.0.0.1:8000/qa/stream \
  -H "content-type: application/json" \
  -d '{"sessionId":"demo-sse","mode":"local","query":"请总结核心结论","history":[]}'
```

你应看到事件流：`message`、`sources`、`messageEnd`（异常时 `error`）。

## 8. 停止服务

在运行 `scripts/dev-up.sh` 的终端按 `Ctrl+C`。

## 9. 常见问题

### 9.1 浏览器提示“无法访问此网页”

优先使用完整 URL：

- `http://localhost:3000/chat`
- 失败再试：`http://127.0.0.1:3000/chat`

若在 WSL/Windows 场景仍失败，改为对外监听启动：

```bash
venv/bin/python -m uvicorn app.kernel_api:app --host 0.0.0.0 --port 8000
cd gateway && GATEWAY_HOST=0.0.0.0 GATEWAY_PORT=8080 npm run dev
cd ../frontend && PORT=3000 npx next dev -H 0.0.0.0 -p 3000
```

然后访问 `http://localhost:3000/chat`。

如果是远程服务器部署，不要直接照搬上面的本地回环地址。应改用同域反向代理，或显式设置公网可达的 `NEXT_PUBLIC_KERNEL_BASE_URL` / `NEXT_PUBLIC_GATEWAY_WS_URL`。

### 9.2 页面打开但偶发 WebSocket warning

若页面状态显示 `Connected`，且可正常问答，可先忽略该 warning；通常是连接初始化阶段的瞬时日志。

### 9.3 PDF 入库日志出现 marker fallback

- 若日志/报告出现 `marker unavailable`，说明当前环境未安装 Marker，可执行 `venv/bin/python -m pip install marker-pdf`。
- 若出现 `marker parse timeout`，提高 `marker_timeout_sec` 或先设置 `marker_enabled=false` 回滚到 legacy 解析。

## 10. 本地模型主路径（Ollama）

如需启用本地 `embedding/rerank/rewrite`，请参考：

- `docs/local-llm-bootstrap.md`

包含一键安装脚本、健康检查、vLLM 可选路径和外部 API 回滚步骤。
