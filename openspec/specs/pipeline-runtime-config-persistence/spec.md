# pipeline-runtime-config-persistence 规范

## 目的
定义 Pipeline 运行态配置的持久化、管理接口与统一概览输出，确保前端和导入链路能够共享一致的 Marker 运行态语义。

## 需求
### 需求:系统必须持久化 Pipeline 运行态配置
系统必须提供独立的 pipeline runtime 配置持久化能力，至少覆盖 Marker tuning 参数：`recognition_batch_size`、`detector_batch_size`、`layout_batch_size`、`ocr_error_batch_size`、`table_rec_batch_size`、`model_dtype`。系统还必须持久化 Marker LLM runtime 配置，包括 `use_llm` 开关、`llm_service` 标识以及当前服务所需的连接字段；读取时必须返回当前保存值、有效回退值与字段来源。

#### 场景:保存并读取 pipeline runtime 配置
- **当** 管理员保存 pipeline runtime 配置
- **那么** 系统必须在后续读取中返回完整字段且字段语义一致

#### 场景:保存并读取 Marker LLM runtime 配置
- **当** 管理员保存 `ClaudeService` 及其 `claude_api_key`、`claude_model_name`
- **那么** 系统必须在后续读取中返回完整字段、字段来源与脱敏后的摘要信息

### 需求:系统必须提供 pipeline runtime 管理接口
系统必须提供管理接口用于读取与保存 pipeline runtime 配置，并返回字段级校验错误，禁止返回无上下文通用错误；对于不同 `llm_service`，系统必须根据 provider 约束返回对应字段错误而不是统一报错。

#### 场景:读取配置
- **当** 前端请求 pipeline runtime 配置
- **那么** 系统必须返回当前生效配置与默认回退值

#### 场景:保存非法配置
- **当** 请求中包含非法批大小或不支持的 dtype
- **那么** 系统必须返回字段级错误信息并拒绝写入

#### 场景:保存 Vertex 配置缺少 project id
- **当** 请求包含 `llm_service=marker.services.vertex.GoogleVertexService` 且缺少 `vertex_project_id`
- **那么** 系统必须返回 `vertex_project_id` 的字段级错误信息并拒绝写入

### 需求:系统必须提供运行态概览聚合输出
系统必须提供统一运行态概览输出，聚合 LLM stage 与 pipeline runtime 配置，并给出状态等级（`READY`/`DEGRADED`/`BLOCKED`/`ERROR`）与原因列表。对于 Marker pipeline，概览输出还必须包含 `use_llm`、`llm_service`、最近一次降级状态、产物健康摘要与可直接渲染的 UI 文案。系统还必须输出按阶段归档的最近完成时间，供 `import-latest`、`marker-artifacts` 与 runtime overview 以一致语义判断各类产物是否过期。

#### 场景:业务页面读取统一概览
- **当** 对话页或壳层请求运行态概览
- **那么** 系统必须一次返回可直接渲染的模型摘要、pipeline tuning 摘要与状态等级

#### 场景:业务页面读取包含降级摘要的统一概览
- **当** 对话页、知识处理页或设置页请求运行态概览
- **那么** 系统必须一次返回模型摘要、pipeline tuning 摘要、Marker LLM 摘要、最近一次降级状态与产物健康信息

#### 场景:按阶段时间判断产物 stale
- **当** 后端聚合 `import-latest` 或 `marker-artifacts` 数据
- **那么** 系统必须返回 Import、Clean、Index、Graph Build 的阶段级 `updated_at`，并使用与产物 `related_stage` 对应的时间判断 stale，而不是统一对比单一全局更新时间
