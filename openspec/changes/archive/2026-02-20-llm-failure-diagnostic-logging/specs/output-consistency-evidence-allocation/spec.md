## MODIFIED Requirements

### 需求:输出字段一致性
系统必须输出统一 QA JSON 结构，并且必须包含 `question`、`mode`、`scope_mode`、`query_used`、`rewrite_rule_query`、`rewrite_llm_query`、`rewrite_llm_used`、`rewrite_llm_fallback`、`calibrated_query`、`papers_ranked`、`evidence_grouped`、`answer`、`answer_citations`、`final_decision`、`output_warnings`。当 LLM 调用失败并发生降级时，输出还必须包含可序列化的失败诊断字段（例如 `rewrite_llm_diagnostics`、`answer_llm_diagnostics`），用于解释 fallback 根因。

#### 场景:输出字段齐全
- **当** QA 流程完成一次回答生成
- **那么** 最终 JSON 必须包含上述字段，且字段类型可序列化

#### 场景:LLM 失败时输出诊断字段
- **当** rewrite 或 answer LLM 调用失败并触发降级
- **那么** 最终 JSON 必须包含对应阶段的诊断对象，且 `reason` 与 `output_warnings` 中的 fallback warning 一致

### 需求:证据充分时必须支持 LLM 约束生成
系统必须在 Sufficiency Gate 判定证据充分且 `answer_use_llm=true` 时，支持基于本轮 `evidence_grouped` 的 LLM 生成回答；若 LLM 调用失败必须降级到模板回答，并记录失败诊断信息用于排障。

#### 场景:证据充分触发 LLM 回答
- **当** `answer_use_llm=true` 且 Sufficiency Gate 判定充分
- **那么** 系统必须尝试 `llm_answer_with_evidence`，并仅使用本轮 `evidence_grouped` 作为事实来源

#### 场景:LLM 回答失败降级模板
- **当** `llm_answer_with_evidence` 调用超时、限流、空响应、HTTP 错误、网络异常或解析失败
- **那么** 系统必须回退到模板回答路径并保持流程不中断，同时输出与失败原因一致的 answer 诊断对象
