## 为什么

当前项目虽支持多处模型路由与配置，但前端仅可配置 `answer/embedding/rerank` 三段，且 `rewrite` 与 `graph entity` 等模型位点无法在统一面板中管理。对于以外部 API 为主、并希望在个人 8GB 显存设备上优先本地化低成本链路（embedding/rewrite）的场景，现有配置面不够完整，导致部署与运维成本偏高。

## 变更内容

- 扩展“模型设置”前端与后端管理接口，从“三段配置”升级为“全模型配置”视图，覆盖在线问答与离线图构建所需的模型位点。
- 将 `embedding`、`rewrite` 设为本地优先路径，并为 `rerank` 保留外部 API / vLLM 兼容默认值，以适配个人开发机的实际可用性边界。
- 保留 `answer` 外部 API 兼容路径，同时支持在同一配置面板中统一查看和编辑。
- 将 `rewrite` 从“运行时跟随 answer”改为可独立配置路由，避免耦合带来的调试与回滚困难。
- 增加本地模型安装与接入的明确交付：提供本地模型准备清单、安装命令或脚本入口、首轮拉起校验步骤、失败诊断与回滚步骤。
- 在变更范围内明确两类本地模型安装目标：`embedding`、`rewrite`；`rerank` 维持远端兼容默认值。
- 明确 8GB 设备默认模型清单：
  - `embedding` 默认 `bge-m3`，备选 `nomic-embed-text`
  - `rewrite` 默认 `qwen2.5:3b`，备选 `qwen2.5:1.5b`
  - `rerank` 默认保留远端兼容模型，例如 `Qwen/Qwen3-Reranker-8B`
- 明确安装与运行主路径采用 `Ollama`（`vLLM` 作为可选高级路径，不作为首轮必选依赖）。
- 明确验收口径：本地 `embedding/rewrite` 必须通过连通性检查（模型可发现与可调用）、基础质量回归（代表性问答集不劣化到不可用）与一键回滚到外部 API 的可操作性验证。

## 功能 (Capabilities)

### 新增功能
- `local-llm-bootstrap-and-defaults`: 定义本地模型安装、默认路由预置与运维校验规范，确保个人开发机可复现地启用本地 `embedding/rewrite`，并为 `rerank` 保留外部兼容路径。

### 修改功能
- `frontend-llm-connection-settings`: 从三段配置扩展为全模型配置视图，并为本地两段与远端 rerank 提供默认值预填。
- `frontend-stage-llm-settings`: 调整 stage 组织与交互，支持除 `answer/embedding/rerank` 外的模型位点展示与保存。
- `llm-runtime-config-persistence`: 扩展运行时配置持久化结构，纳入 `rewrite` 及其他模型位点，取消 `rewrite` 强绑定 `answer` 的隐式覆盖语义。
- `query-rewriting`: 将 rewrite 路由从“跟随 answer”升级为可独立配置与可观测。
- `llm-entity-extraction-for-graph`: 使图实体抽取模型配置可被统一管理与持久化读取。

## 影响

- 受影响前端：模型设置页的字段模型、默认值策略、保存/回显/错误提示逻辑。
- 受影响后端：`/api/admin/llm-config` 的请求与响应结构、配置校验、运行时持久化读取/写入逻辑。
- 受影响配置：`configs/default.yaml` 与运行时配置文件字段语义（新增字段、历史兼容映射）。
- 运维与文档：需新增“本地模型安装与接入”说明（含先决条件、安装步骤、模型拉取、健康检查、压测建议），以及外部 API 与本地模式切换回滚指南。
- 测试与验收：需新增/更新回归用例，覆盖 `embedding/rewrite` 本地路由生效、前端全模型配置保存回显、以及本地不可用时的降级与回滚路径。
