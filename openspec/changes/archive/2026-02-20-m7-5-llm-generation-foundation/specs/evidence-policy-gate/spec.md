## ADDED Requirements

### 需求:LLM 回答输出必须经过 Gate 二次校验
系统必须对 `llm_answer_with_evidence` 的输出执行与模板回答一致的 evidence policy gate 校验，禁止绕过门控直接输出。

#### 场景:LLM 回答进入统一门控
- **当** 上游生成来源为 `llm_answer_with_evidence`
- **那么** 系统必须执行关键结论覆盖、citation 可定位与语义一致校验后才可输出最终回答

## MODIFIED Requirements

### 需求:关键结论必须绑定可追溯 citation
系统必须对回答中的关键结论执行引用覆盖校验。关键结论至少包括数字陈述、实验结果陈述、定义性陈述与结论性判断句。每条关键结论必须关联至少一个 citation，且 citation 必须包含 `chunk_id`、`paper_id` 与 `section_page`。

#### 场景:关键结论覆盖通过
- **当** 系统完成回答草稿并识别出关键结论集合
- **那么** 每条关键结论必须至少绑定 1 条包含 `chunk_id`、`paper_id` 与 `section_page` 的 citation，未覆盖则不得进入最终回答

### 需求:证据不足必须进入 M8 Sufficiency Gate
当任一关键结论缺失 citation、citation 不可定位、语义支撑不足或 Gate 明确判定不通过时，系统必须进入 M8 Sufficiency Gate，禁止输出强断言回答，并追加 `insufficient_evidence_for_answer` 告警。

#### 场景:触发 M8 门控
- **当** 关键结论校验存在未通过项或 Gate 判定不通过
- **那么** 系统必须输出门控后的弱回答模板，并在 `output_warnings` 中包含 `insufficient_evidence_for_answer`

## REMOVED Requirements
