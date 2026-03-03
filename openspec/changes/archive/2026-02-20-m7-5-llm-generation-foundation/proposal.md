## 为什么

当前系统在 Query Rewriting 与回答生成上主要依赖规则和模板路径，面对复杂问法与证据组织时灵活性不足。M7.5 需要在不破坏 M2~M7 既有行为的前提下，引入可降级、可追溯的 LLM 生成层，并保证调用失败不影响主流程可用性。

## 变更内容

- 在检索前链路新增可选 `llm_rewrite`：当 `rewrite_use_llm=true` 且 `scope_mode!=clarify_scope` 时尝试 LLM 改写，失败回退规则改写。
- 在检索后链路新增 `llm_answer_with_evidence`：仅在 Sufficiency Gate 判定证据充分时启用基于 evidence 的受约束生成。
- 新增统一 LLM 配置项与超时/重试/降级开关，并接入 `SILICONFLOW_API_KEY`。
- 扩展输出与追踪字段：`rewrite_llm_query`、`rewrite_llm_used`、`rewrite_llm_fallback`，并强化 `answer_citations` 子集约束与关键结论映射。
- 强化失败兜底：任一 LLM 调用失败（超时/限流/空响应）必须降级，不中断主流程。
- 增补 M7.5 验收评估与报告产物：`reports/m7_5_llm_rewrite_eval.md`、`reports/m7_5_llm_answer_eval.md`。

## 功能 (Capabilities)

### 新增功能
- `llm-generation-foundation`: 定义统一的 LLM 提供方/模型配置、调用超时重试策略、降级协议、运行追踪与报告验收要求。

### 修改功能
- `query-rewriting`: 从规则改写扩展为“规则 + 可选 LLM 改写”，并新增字段与失败回退约束。
- `output-consistency-evidence-allocation`: 将回答路径扩展为“模板回答 + 可选 evidence-grounded LLM 回答”，并强化 citation 子集与关键结论对齐校验。
- `evidence-policy-gate`: 明确与 `llm_answer` 的门控衔接，保证证据不足时强制弱回答降级。

## 影响

- 受影响代码：重写模块、回答生成模块、Sufficiency Gate 与输出组装逻辑、配置加载与运行日志。
- 受影响接口：最终 QA JSON 字段扩展（新增 rewrite LLM 相关字段，强化 citation 约束）。
- 受影响依赖：新增/接入 SiliconFlow LLM 调用客户端（使用 `SILICONFLOW_API_KEY`）。
- 风险与成本：LLM 幻觉、时延、限流与费用波动；通过 evidence 边界、门控校验、失败降级和可追踪日志控制风险。
