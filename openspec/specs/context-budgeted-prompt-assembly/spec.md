# context-budgeted-prompt-assembly 规范

## 目的
在 LLM Answer 调用前提供统一的上下文预算控制与组装，避免上下文超限并提高证据保真度。

## 需求
### 需求:系统必须在 LLM 调用前执行统一的上下文预算组装
系统必须在 M7.5-B 调用前，将 `system_prompt`、`user_prompt`、`chat_history` 与 `evidence_grouped` 组装为单一 `assembled_prompt`，并必须产出 `prompt_tokens_est` 作为本次输入消耗估算值。

#### 场景:预算内直接组装
- **当** 初步估算 `total_tokens <= max_context_tokens`
- **那么** 系统必须直接返回包含全部输入的 `assembled_prompt`，并输出 `prompt_tokens_est`

### 需求:超预算时必须按固定优先级裁剪
当初步估算 `total_tokens > max_context_tokens` 时，系统必须按以下顺序裁剪并循环重估直到满足预算：先裁剪最老 `chat_history`，后裁剪 `evidence_grouped`，且必须始终保留当前轮用户问题。

#### 场景:先裁历史再裁证据
- **当** 初始 token 超过预算
- **那么** 系统必须先删除最老历史记录，且仅在历史已缩减到 1 轮后才允许开始裁剪证据

### 需求:证据裁剪必须优先丢弃边缘图扩展证据
当进入证据裁剪阶段时，系统必须优先丢弃 `payload.source=graph_expand` 且 `score_rerank` 较低的 chunk，并必须优先保留 `payload.source` 为 `bm25` 或 `dense` 的高分核心证据。

#### 场景:图扩展低分证据优先被丢弃
- **当** 证据裁剪开始且候选中同时存在 `graph_expand` 与 `bm25/dense` 来源
- **那么** 系统必须先从低 `score_rerank` 的 `graph_expand` chunk 开始移除，再考虑核心来源证据

### 需求:系统必须返回裁剪清单与兜底告警
系统必须返回 `discarded_evidence` 列表以记录被裁剪 chunk；若裁剪后证据数量小于 1，系统必须拒绝调用 LLM，追加 `output_warnings += context_overflow_fallback`，并返回固定提示“检索内容过长，无法生成答案”。

#### 场景:证据被裁空触发短路
- **当** 裁剪结束后剩余证据数 `< 1`
- **那么** 系统必须不调用 LLM，并返回兜底错误信息与 `context_overflow_fallback` 告警

### 需求:系统必须在极端负载下避免上下文超限异常
系统必须在 `top_n_evidence=30` 且包含大量长图扩展文本的极端输入下触发裁剪逻辑，且最终 LLM 调用不得抛出 `Token Limit Exceeded` 异常。

#### 场景:极端场景验收通过
- **当** 测试构造超长证据并执行完整链路
- **那么** `discarded_evidence` 必须非空，且调用链路不得出现 Token 上下文超限错误
