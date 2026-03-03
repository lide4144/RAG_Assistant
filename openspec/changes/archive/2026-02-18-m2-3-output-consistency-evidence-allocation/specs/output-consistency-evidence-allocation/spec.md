## 新增需求

### 需求:输出字段一致性
系统必须输出统一 QA JSON 结构，并且必须包含 `question`、`mode`、`scope_mode`、`query_used`、`rewrite_rule_query`、`calibrated_query`、`papers_ranked`、`evidence_grouped`、`answer`、`answer_citations`、`output_warnings`。

#### 场景:输出字段齐全
- **当** QA 流程完成一次回答生成
- **那么** 最终 JSON 必须包含上述字段，且字段类型可序列化

### 需求:paper 与 evidence 一致性修复
系统必须保证 `papers_ranked` 前 N（默认 5）中的每篇论文都在 `evidence_grouped` 中至少有 1 条证据。若 Top paper 无证据，系统必须自动补选该 paper 的最高分 supporting chunk，并在 `output_warnings` 增加 `top_paper_has_no_evidence_fixed`。

#### 场景:Top paper 无证据时自动修复
- **当** `papers_ranked[0]` 对应论文在 `evidence_grouped` 中证据为空
- **那么** 系统必须补入至少 1 条来自该论文 `supporting_chunks` 的证据并记录修复 warning

### 需求:证据分配上限与来源约束
系统必须执行 evidence 分配策略：每篇论文最多 `max_evidence_per_paper`（默认 2）条、最少 1 条（当该论文被展示时）；`evidence_grouped` 最多展示 `max_papers_display`（默认 6）篇；证据必须来自该论文 `supporting_chunks`，且 quote 必须来自原始 `text` 字段。

#### 场景:按论文限额分配证据
- **当** 候选证据覆盖超过 6 篇论文或单篇论文超过 2 条高分证据
- **那么** 系统必须按配置截断并保持每个展示论文至少 1 条证据

#### 场景:quote 来源受控
- **当** 系统生成 evidence quote
- **那么** quote 必须来自原始 `text`，长度应在 50~120 字之间；若原文不足允许短 quote 但不得为空

### 需求:回答引用可追溯
系统必须输出 `answer_citations=list[{chunk_id, paper_id, section_page}]`，并保证其中每个 citation 对应 `evidence_grouped` 内已展示证据。

#### 场景:citation 与 evidence 对齐
- **当** 回答包含关键结论
- **那么** 系统必须在 `answer_citations` 中给出支撑 chunk，且每个 chunk 均可在 `evidence_grouped` 找到

### 需求:证据不足降级
当证据总量不足或证据质量不足以支撑结论时，系统必须使用弱回答模板并提示补充线索，禁止生成具体编造结论，同时在 `output_warnings` 中增加 `insufficient_evidence_for_answer`。

#### 场景:证据不足触发降级
- **当** evidence 总数小于 2 或 evidence 为空，或 evidence 全为高噪声类型
- **那么** 系统必须输出弱回答模板并记录 `insufficient_evidence_for_answer`

### 需求:summary shell 仍主导时告警
当 M2.2 已执行 summary cue 抑制后，若 Top evidence 的 summary shell 占比仍超过 60%，系统必须在输出中记录 `summary_shell_still_dominant`。

#### 场景:retry 后仍被 shell 主导
- **当** query retry 后 Top evidence 的 summary shell 占比仍大于 60%
- **那么** 系统必须追加 `summary_shell_still_dominant` 到 `output_warnings`
