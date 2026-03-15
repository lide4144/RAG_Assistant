# Planner Runtime Contract

本文件定义 agent-first 路线下 Python planner runtime 的最小实现契约。

## 顶层边界

- `LLM Planner runtime` 负责意图理解、tool 选择、执行顺序、澄清与降级决策。
- `tool layer` 负责承接 planner 发起的结构化调用，不承担顶层规划。
- `deterministic kernel` 负责 evidence gate、citation、任务状态、trace 落盘和稳定流水线执行。

## 稳定状态字段

`agent-first-v1` 运行时保证以下顶层字段稳定存在：

- `request`
- `planner`
- `tool_calls`
- `route`
- `fallback`
- `response`
- `selected_path`
- `execution_trace`
- `short_circuit`
- `truncated`

扩展字段允许放在 `tool_results`、`runtime` 等 envelope 中，不影响上层调用契约。

## Tool Contract

每个 planner runtime tool call 至少包含：

- `id`
- `tool_name`
- `query`
- `depends_on`
- `produces`
- `params`
- `route`
- `passthrough`
- `status`

当前注册的 runtime tools：

- `fact_qa`
- `catalog_lookup`
- `cross_doc_summary`
- `control`
- `paper_assistant`

## Fallback 分类

- `planner_runtime_fallback`: 规划为空、超步数、未注册 tool 或 runtime 异常时触发。
- `tool_fallback`: tool 依赖不满足、short-circuit、证据不足等执行级失败时触发。

Gateway 仅识别入口和兼容回退，不复制 planner/tool 语义。
