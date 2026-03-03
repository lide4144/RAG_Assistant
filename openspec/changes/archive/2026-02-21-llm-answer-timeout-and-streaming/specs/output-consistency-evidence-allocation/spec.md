## ADDED Requirements

### 需求:流式回答观测字段必须可追踪
当回答阶段启用流式时，系统必须输出可追踪字段（至少包含流式是否启用、是否实际走流、首字延迟或回退原因），用于运行审计与容量分析。

#### 场景:流式启用时字段落盘
- **当** `answer_stream_enabled=true` 且本轮回答执行结束
- **那么** 运行产物必须包含流式观测字段，并与 warning/diagnostics 语义一致

## MODIFIED Requirements

### 需求:输出字段一致性
系统必须输出统一 QA JSON 结构，并且必须包含 `question`、`mode`、`scope_mode`、`query_used`、`rewrite_rule_query`、`rewrite_llm_query`、`rewrite_llm_used`、`rewrite_llm_fallback`、`calibrated_query`、`papers_ranked`、`evidence_grouped`、`answer`、`answer_citations`、`final_decision`、`output_warnings`。当启用流式回答时，必须额外包含流式观测字段并保证类型可序列化。

#### 场景:输出字段齐全
- **当** QA 流程完成一次回答生成
- **那么** 最终 JSON 必须包含基础字段；若启用流式则必须包含对应流式观测字段

### 需求:回答引用可追溯
系统必须输出 `answer_citations=list[{chunk_id, paper_id, section_page}]`，并保证回答中的关键结论（含数字、指标、定义句与结论性判断）均可映射到 citation。`answer_citations` 必须是 `evidence_grouped` 的子集，禁止引用未展示证据。

#### 场景:citation 与关键结论对齐
- **当** 回答包含关键结论（含数字、指标、定义句与结论性判断）
- **那么** 系统必须为每条关键结论输出 citation，且 citation 的 `chunk_id` 必须可在 `evidence_grouped` 找到

#### 场景:citation 不属于 evidence 子集
- **当** 任一 citation 的 `chunk_id` 不存在于 `evidence_grouped`
- **那么** 系统必须拒绝该回答并进入降级路径，禁止输出不可追溯强断言

## REMOVED Requirements
