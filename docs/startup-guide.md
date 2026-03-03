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

说明：`npm audit` 漏洞提示不会阻塞本地启动；不要直接运行 `npm audit fix --force`，避免破坏性升级。

## 4. 一键启动（推荐）

```bash
cd /home/programer/RAG_GPTV1.0
scripts/dev-up.sh
```

启动成功后会打印：

- `python-kernel-fastapi pid=... url=http://127.0.0.1:8000`
- `gateway pid=... url=http://127.0.0.1:8080`
- `frontend pid=... url=http://127.0.0.1:3000`

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

### 9.2 页面打开但偶发 WebSocket warning

若页面状态显示 `Connected`，且可正常问答，可先忽略该 warning；通常是连接初始化阶段的瞬时日志。
