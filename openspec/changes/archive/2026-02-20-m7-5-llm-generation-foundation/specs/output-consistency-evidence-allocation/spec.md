## ADDED Requirements

### 需求:证据充分时必须支持 LLM 约束生成
系统必须在 Sufficiency Gate 判定证据充分且 `answer_use_llm=true` 时，支持基于本轮 `evidence_grouped` 的 LLM 生成回答；若 LLM 调用失败必须降级到模板回答。

#### 场景:证据充分触发 LLM 回答
- **当** `answer_use_llm=true` 且 Sufficiency Gate 判定充分
- **那么** 系统必须尝试 `llm_answer_with_evidence`，并仅使用本轮 `evidence_grouped` 作为事实来源

#### 场景:LLM 回答失败降级模板
- **当** `llm_answer_with_evidence` 调用超时、限流、空响应或解析失败
- **那么** 系统必须回退到模板回答路径并保持流程不中断

## MODIFIED Requirements

### 需求:输出字段一致性
系统必须输出统一 QA JSON 结构，并且必须包含 `question`、`mode`、`scope_mode`、`query_used`、`rewrite_rule_query`、`rewrite_llm_query`、`rewrite_llm_used`、`rewrite_llm_fallback`、`calibrated_query`、`papers_ranked`、`evidence_grouped`、`answer`、`answer_citations`、`final_decision`、`output_warnings`。

#### 场景:输出字段齐全
- **当** QA 流程完成一次回答生成
- **那么** 最终 JSON 必须包含上述字段，且字段类型可序列化

### 需求:回答引用可追溯
系统必须输出 `answer_citations=list[{chunk_id, paper_id, section_page}]`，并保证回答中的关键结论（含数字、指标、定义句与结论性判断）均可映射到 citation。`answer_citations` 必须是 `evidence_grouped` 的子集，禁止引用未展示证据。

#### 场景:citation 与关键结论对齐
- **当** 回答包含关键结论（含数字、指标、定义句与结论性判断）
- **那么** 系统必须为每条关键结论输出 citation，且 citation 的 `chunk_id` 必须可在 `evidence_grouped` 找到

#### 场景:citation 不属于 evidence 子集
- **当** 任一 citation 的 `chunk_id` 不存在于 `evidence_grouped`
- **那么** 系统必须拒绝该回答并进入降级路径，禁止输出不可追溯强断言

### 需求:证据不足降级
当证据总量不足、证据质量不足、关键结论追溯校验失败或 Gate 判定不通过时，系统必须输出弱回答模板并追加 `insufficient_evidence_for_answer`，禁止自由发挥。

#### 场景:证据不足触发降级
- **当** evidence 总数小于阈值、evidence 为空或 Gate 判定不通过
- **那么** 系统必须输出弱回答模板并记录 `insufficient_evidence_for_answer`

## REMOVED Requirements
