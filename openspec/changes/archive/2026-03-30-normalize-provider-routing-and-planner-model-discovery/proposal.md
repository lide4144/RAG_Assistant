## 为什么

当前运行时配置对 SiliconFlow 存在两套不一致语义：一部分聊天/规划链路把它当作 OpenAI-compatible 服务使用，另一部分配置与文档又把 `provider=siliconflow` 当作通用 provider 直接持久化，导致 LiteLLM 路径出现 provider 解析错误。与此同时，Planner Runtime 设置页虽然支持独立配置，但仍要求管理员手填模型名，和其他模型配置页的探测后选择体验不一致。

## 变更内容

- 将聊天/规划类运行时 LLM 配置统一规范为 OpenAI-compatible provider 语义，使用 `provider=openai` 表示 SiliconFlow 等兼容 OpenAI `/chat/completions` 与 `/models` 的服务。
- 保留 `embedding` 与 `rerank` 的原生 `siliconflow` 语义，不把原生专用接口错误折叠到 OpenAI-compatible provider。
- 要求 Planner Runtime 的持久化、回显与运行态判定使用同一套 provider 规范化语义，避免展示层与执行层不一致。
- 要求前端 Planner Runtime 配置区支持模型探测结果下拉选择，而不是仅支持手填模型名。

## 功能 (Capabilities)

### 新增功能

无

### 修改功能

- `configuration-governance-model`: 明确 OpenAI-compatible provider 与原生 provider 的治理边界与规范化语义。
- `llm-generation-foundation`: 更新聊天/生成链路默认 provider 语义，不再将 OpenAI-compatible 默认值写死为 `siliconflow`。
- `planner-runtime-config-persistence`: 要求 Planner Runtime 的持久化、回显与执行统一使用规范化后的 provider 语义。
- `frontend-llm-connection-settings`: 要求 Planner Runtime 配置区复用模型探测并提供模型下拉选择。

## 影响

- 影响后端运行时配置解析、默认值与持久化回显逻辑。
- 影响前端“模型设置”页中 Planner Runtime 的编辑与模型选择体验。
- 影响 OpenSpec 主规范中 provider 默认值与配置治理语义的表达。
