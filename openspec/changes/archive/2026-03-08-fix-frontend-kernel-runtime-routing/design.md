## 上下文

在 `modernize-rag-saas-workbench-ui-ux` 后，前端新增了多个运行态读取点（壳层、聊天页、设置页）。这些调用统一依赖 `process.env.NEXT_PUBLIC_KERNEL_BASE_URL ?? ''`。当该变量未注入时，请求会变成相对路径 `/api/admin/*`，直接命中 Next 开发服务器（3000），而不是 Kernel（8000）。

实测结果：
- 浏览器请求 `http://127.0.0.1:3000/api/admin/runtime-overview`，返回 404。
- 404 body 为 HTML，部分调用路径直接 `response.json()`，触发 `Unexpected token '<'`。
- `reactStrictMode: true` 在开发环境重复触发 effect，放大日志与报错频率。

## 目标 / 非目标

**目标：**
- 默认本地启动 (`scripts/dev-up.sh`) 下，前端管理接口请求必须稳定命中 Kernel。
- 前端在收到 HTML 或其他非 JSON 错误响应时必须可读降级，不得抛出 JSON 解析异常。
- 在不改变后端 API 契约的前提下修复回归并补齐测试。

**非目标：**
- 不改造 Kernel 端点定义与响应结构。
- 不变更 Gateway WebSocket 协议。
- 不在本变更中做 UI 视觉层重构。

## 决策

1. 决策：将“默认可用”前置到启动脚本，明确注入前端 Kernel 基地址。
- 方案 A（选中）：`scripts/dev-up.sh` 启动前端时注入 `NEXT_PUBLIC_KERNEL_BASE_URL=http://$KERNEL_HOST:$KERNEL_PORT`。
- 方案 B：仅依赖开发者手工配置 `.env.local`。
- 理由：A 可消除默认路径歧义，降低新环境误配率。

2. 决策：前端管理接口读取采用“先判响应类型，再解析 JSON”。
- 方案 A（选中）：封装统一解析函数，先检查 `response.ok` 与 `content-type`，再决定 JSON/text 分支。
- 方案 B：保持各页面直接 `response.json()` 并在 catch 中兜底。
- 理由：A 可避免语义错误（HTML 当 JSON），并提高错误信息可读性。

3. 决策：为 `/api/admin/*` 增加可选 rewrite 作为兼容层（非唯一依赖）。
- 方案 A（选中）：在 `next.config.mjs` 配置 rewrite 到 Kernel，保证未注入时仍可联调。
- 方案 B：不做 rewrite，只依赖 env 注入。
- 理由：A 增强稳健性；env 与 rewrite 双保险可降低回归概率。

## 数据流草图

```text
Browser (frontend)
   │
   ├─ 优先: NEXT_PUBLIC_KERNEL_BASE_URL + /api/admin/*
   │
   └─ 兜底: Next rewrite /api/admin/* -> Kernel :8000
                    │
                    ▼
                FastAPI Kernel
```

```text
HTTP response
   │
   ├─ response.ok && content-type is json -> parse json
   └─ else -> parse text snippet + map user-friendly error
```

## 风险 / 权衡

- [风险] env 注入与 rewrite 同时存在，可能带来配置优先级困惑。
  → 缓解：文档明确“显式 env 优先，rewrite 仅兜底”。

- [风险] 统一解析函数改造范围涉及多个页面，可能漏改。
  → 缓解：以 `/api/admin/*` 关键词全局扫描并补充回归测试。

- [风险] 开发模式下 StrictMode 仍会重复请求。
  → 缓解：本变更不关闭 StrictMode，仅确保重复请求不会产生解析异常与污染性报错。

## Migration Plan

1. 更新 `scripts/dev-up.sh` 注入前端 `NEXT_PUBLIC_KERNEL_BASE_URL`。
2. （可选）在 `frontend/next.config.mjs` 增加 `/api/admin/:path*` rewrite 到 Kernel。
3. 在壳层/聊天/设置页管理接口调用处接入统一响应解析与错误映射。
4. 更新 E2E/单测，覆盖 404 HTML、非 JSON 响应、变量缺失场景。
5. 更新启动文档，明确地址解析优先级与排障路径。

回滚策略：
- 若 rewrite 带来副作用，可单独回滚 rewrite，保留 env 注入与解析容错。
- 若统一解析改造引发行为偏差，可逐页回滚到原逻辑并保留最小错误提示。

## Open Questions

- 是否需要将 `/api/library/*` 与 `/api/tasks/*` 同步纳入 rewrite 兜底范围？
- 是否增加开发环境告警：`NEXT_PUBLIC_KERNEL_BASE_URL` 缺失时在控制台打印一次性提示？
