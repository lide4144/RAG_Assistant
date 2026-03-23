## 为什么

当前系统的配置来源已经分散为 `configs/default.yaml`、`configs/llm_runtime_config.json`、`configs/pipeline_runtime_config.json` 与环境变量四类入口，但它们的职责边界和优先级规则并未被统一建模。结果是前端“模型设置”页只覆盖了部分运行时配置，而大量后端策略仍停留在静态 YAML 中，管理员和开发者都难以快速判断“某个字段是否可在前端调整、最终由谁生效、异常时应回退到哪里”。

随着 LLM stage、Marker runtime、运行态概览与部署方式持续扩展，这种分散语义已经开始影响可维护性、排障效率与后续配置演进。现在需要为整套配置系统建立统一治理模型，明确基线、运行时覆盖与环境强覆盖的职责边界。

## 变更内容

- 统一定义系统配置的治理分层，明确哪些字段属于静态基线配置、哪些字段属于运行时可调整配置、哪些字段属于仅环境变量可控配置。
- 为现有配置字段补充统一的来源优先级语义，至少覆盖 `default.yaml`、runtime 持久化配置与环境变量覆盖关系，并确保运行态概览能够稳定解释字段来源。
- 梳理前端“模型设置”页与后端真实配置面之间的映射关系，明确前端当前覆盖范围、保留范围与后续允许扩展的范围。
- 将证据充分性判定使用的 `sufficiency_judge_*` 小模型配置纳入统一治理范围，并使其进入前端“模型设置”页的运行时配置面。
- 将 `planner_*` 顶层规划模型配置从仅静态 YAML 管理升级为独立的运行时可管理配置面，使管理员能够承担规划模型的成本、切换和回退责任。
- 为后续配置扩展建立规范约束，避免新增字段继续无序散落在 YAML、runtime JSON 与 env 之间。
- 明确前端设置页后续演进约束：设置页的现代化实现需保持 `magic-mcp` 工作流兼容性，界面语言与交互保持中文语境，代码注解保持中文风格。

## 功能 (Capabilities)

### 新增功能

- `configuration-governance-model`: 定义统一的配置治理模型、字段 owner 分类、来源优先级与运行态来源可观测规则。

### 修改功能

- `frontend-llm-connection-settings`: 调整设置页规范，使其显式声明“前端设置不是全量系统配置面”，并约束后续设置页现代化实现保持 `magic-mcp` 兼容性，且保持中文注解风格。
- `llm-runtime-config-persistence`: 调整 LLM runtime 持久化规范，使其纳入统一配置治理模型，并补入 `sufficiency_judge` runtime stage。
- `planner-runtime-config-persistence`: 新增 Planner Runtime 持久化规范，使顶层规划模型配置纳入统一治理模型，并以前端独立高风险面板方式管理。
- `pipeline-runtime-config-persistence`: 调整 pipeline runtime 持久化规范，使其与统一字段来源语义、owner 分类和运行态概览保持一致。

## 影响

- 受影响规范：
  - `openspec/specs/frontend-llm-connection-settings/spec.md`
  - `openspec/specs/llm-runtime-config-persistence/spec.md`
  - `openspec/specs/planner-runtime-config-persistence/spec.md`
  - `openspec/specs/pipeline-runtime-config-persistence/spec.md`
- 预期将影响后端配置加载、运行态来源展示与设置页字段边界定义。
- 预期将影响前端设置页的后续设计与实现约束，但本提案阶段不涉及直接应用代码实现。
