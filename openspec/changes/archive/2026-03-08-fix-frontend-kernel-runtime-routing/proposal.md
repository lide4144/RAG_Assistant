## 为什么

`modernize-rag-saas-workbench-ui-ux` 在壳层/聊天/设置页新增了对运行态接口的常驻读取，但前端默认未注入 `NEXT_PUBLIC_KERNEL_BASE_URL`，导致请求落到 `localhost:3000`（Next）而非 `:8000`（Kernel），触发 404 与前端解析异常。该问题会在开发环境被 StrictMode 重放放大，影响可用性与排障效率。

## 变更内容

- 修正前端到 Kernel 管理接口的地址解析策略，确保默认开发路径不会请求到不存在的 Next API 地址。
- 为本地一键启动脚本补充前端环境注入（`NEXT_PUBLIC_KERNEL_BASE_URL`），保证三服务默认联调即正确路由。
- 增加前端对非 JSON 响应的容错处理（按 `content-type` 与 `response.ok` 分支），避免出现 `Unexpected token '<'`。
- 补充回归测试覆盖：未注入地址、404/HTML 响应、StrictMode 重放下的错误可控性。

## 功能 (Capabilities)

### 新增功能
<!-- 无 -->

### 修改功能
- `frontend-saas-shell-navigation`: 壳层运行态请求必须具备稳定的 Kernel 路由与失败降级提示，不得依赖偶然环境变量。
- `frontend-chat-focused-experience`: 聊天页运行态摘要请求必须具备同样的路由稳定性与非 JSON 容错。
- `frontend-stage-llm-settings`: 设置页对 `/api/admin/*` 管理接口的加载与保存流程必须在非 JSON/错误响应时提供可读错误并保持页面可用。

## 影响

- 前端代码：`frontend/components/app-shell.tsx`、`frontend/components/chat-shell.tsx`、`frontend/components/settings-shell.tsx`、可能新增统一 fetch/parse 工具。
- 启动脚本：`scripts/dev-up.sh`（前端环境注入）。
- Next 配置：`frontend/next.config.mjs`（如采用 rewrites 方案）。
- 测试：`frontend/tests/*` 需新增或更新接口路由与错误处理用例。
