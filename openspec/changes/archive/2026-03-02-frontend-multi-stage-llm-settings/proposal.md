## 为什么

当前后端已经支持按 `answer/embedding/rerank` 三个 stage 持久化与读取运行时路由配置，但前端 `LLM CONNECTION SETTINGS` 仍是单路表单。前后端能力不一致会导致新能力不可操作、用户误以为配置未生效，并增加联调与运维排障成本。

## 变更内容

- 将前端 LLM 配置面板从“单路配置”升级为“三路配置”（answer、embedding、rerank）。
- 更新前端与内核管理接口的契约：
  - `GET /api/admin/llm-config` 返回三路配置对象。
  - `POST /api/admin/llm-config` 支持三路保存载荷（并保持旧单路请求兼容）。
- 在 UI 中补充 stage 级别的检测、保存反馈和错误提示，避免误配。
- 更新前端端到端测试与使用文档，覆盖三路配置流程。

## 功能 (Capabilities)

### 新增功能
- `frontend-stage-llm-settings`: 提供 answer/embedding/rerank 三路可视化配置、保存与状态反馈。

### 修改功能
- `frontend-llm-connection-settings`: 将现有单路设置面板扩展为三路设置交互。
- `llm-runtime-config-persistence`: 将运行时配置管理接口契约从单路字段扩展为三路结构并保留兼容。

## 影响

- 受影响代码：
  - 前端配置面板与状态管理：`frontend/components/chat-shell.tsx`
  - 前端 e2e 测试：`frontend/tests/llm-settings-panel.spec.ts`
  - 后端管理接口响应/请求结构：`app/kernel_api.py`、`app/admin_llm_config.py`
- 受影响 API：`/api/admin/llm-config` 的请求/响应字段扩展。
- 兼容性：保留旧单路请求兼容，避免已有调用方立即中断。
