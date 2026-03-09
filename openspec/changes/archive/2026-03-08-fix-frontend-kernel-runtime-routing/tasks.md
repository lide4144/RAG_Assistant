## 1. 路由与配置修复

- [x] 1.1 在 `scripts/dev-up.sh` 启动前端时注入 `NEXT_PUBLIC_KERNEL_BASE_URL=http://$KERNEL_HOST:$KERNEL_PORT`
- [x] 1.2 在 `frontend/next.config.mjs` 增加 `/api/admin/:path*` 到 Kernel 的 rewrite 兜底（保留 env 优先）
- [x] 1.3 更新启动文档，明确前端管理接口路由优先级（env > rewrite）与排障步骤

## 2. 前端响应容错修复

- [x] 2.1 抽取统一管理接口响应解析工具：先检查 `response.ok` 与 `content-type`，再执行 JSON 解析
- [x] 2.2 在 `app-shell`、`chat-shell`、`settings-shell` 接入统一解析与可读错误提示
- [x] 2.3 确认开发模式 StrictMode 重放下不会再出现 `Unexpected token '<'` 解析异常

## 3. 测试与回归

- [x] 3.1 增加/更新前端测试：`/api/admin/runtime-overview` 返回 404 HTML 时页面可用且提示正确
- [x] 3.2 增加/更新设置页测试：`/api/admin/llm-config` 非 JSON 错误响应不触发崩溃
- [x] 3.3 执行 E2E 回归覆盖壳层/聊天/设置三页面的运行态请求路径与错误处理
