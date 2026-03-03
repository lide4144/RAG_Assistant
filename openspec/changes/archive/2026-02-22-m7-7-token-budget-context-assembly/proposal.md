## 为什么

在引入图扩展与重排后，证据体量与多轮历史会显著推高上下文长度，导致 LLM 调用接近或超过窗口上限，并放大中部信息丢失风险。需要一个可预测、可审计的 Token 预算与裁剪流程，保证回答链路在高负载场景下仍稳定可用。

## 变更内容

- 新增“Token 预算管理与 Context 组装”模块，统一组装 system prompt、user prompt、多轮历史与分组证据。
- 定义 `max_context_tokens` 下的硬约束裁剪策略，超预算时按固定优先级裁剪：
  - 先裁剪最老历史轮次；
  - 再裁剪边缘证据（优先丢弃 `graph_expand` 且 rerank 低分 chunk）；
  - 若证据被裁至 0，触发溢出兜底并拒绝调用 LLM。
- 输出结构化结果：`assembled_prompt`、`discarded_evidence`、`prompt_tokens_est`，并补充溢出告警。
- 增加极端场景验收，验证不会再触发 `Token Limit Exceeded`。

## 功能 (Capabilities)

### 新增功能
- `context-budgeted-prompt-assembly`: 基于显式 token 预算进行 prompt 组装、历史/证据裁剪与溢出兜底，向 LLM Answer 阶段输出安全上下文。

### 修改功能
- `multi-turn-session-state`: 明确历史记录在预算受限场景下的保留下限与裁剪顺序。
- `rerank-evidence-selection`: 明确在预算裁剪阶段对来源与 rerank 分数的保留/丢弃优先级。

## 影响

- 受影响代码：M7.5-B 之前的 context 组装链路、会话历史聚合逻辑、证据选择后处理逻辑。
- 受影响接口：向 LLM 调用层传入的 prompt 与元信息字段（新增 token 估算和丢弃清单）。
- 受影响观测：新增 context overflow 告警与裁剪统计，便于排障与容量调参。
