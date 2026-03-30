## 1. Provider 语义规范

- [x] 1.1 更新 `configuration-governance-model` 与 `llm-generation-foundation` 增量规范，明确 OpenAI-compatible 与原生 provider 的治理边界
- [x] 1.2 核对聊天/规划类运行时配置默认值与持久化语义，确认不再把 SiliconFlow 品牌名当作通用 provider 写入主规范

## 2. Planner Runtime 配置一致性

- [x] 2.1 更新 `planner-runtime-config-persistence` 增量规范，要求保存、回显、运行态概览与执行链使用一致的 provider 规范化语义
- [x] 2.2 核对 Planner Runtime 的旧配置兼容与 API Key 解析语义，确认规范可覆盖历史配置迁移

## 3. 前端模型选择体验

- [x] 3.1 更新 `frontend-llm-connection-settings` 增量规范，要求 Planner Runtime 复用模型探测并提供模型下拉选择
- [x] 3.2 核对前端对 `embedding`、`rerank` 与 OpenAI-compatible 链路的 provider 预设表达，确保规范与当前实现一致
