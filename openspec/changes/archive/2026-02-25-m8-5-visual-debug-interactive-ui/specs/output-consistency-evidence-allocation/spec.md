## MODIFIED Requirements

### 需求:回答引用可追溯
系统必须输出 `answer_citations=list[{chunk_id, paper_id, section_page}]`，并保证回答中的关键结论（含数字、指标、定义句与结论性判断）均可映射到 citation。`answer_citations` 必须是 `evidence_grouped` 的子集，禁止引用未展示证据。系统必须保证回答中的引用标记（如 `[1]`、`[2]`）与 `answer_citations` 建立稳定映射，使 UI 可按编号交互定位对应证据。

#### 场景:citation 与关键结论对齐
- **当** 回答包含关键结论（含数字、指标、定义句与结论性判断）
- **那么** 系统必须为每条关键结论输出 citation，且 citation 的 `chunk_id` 必须可在 `evidence_grouped` 找到

#### 场景:citation 不属于 evidence 子集
- **当** 任一 citation 的 `chunk_id` 不存在于 `evidence_grouped`
- **那么** 系统必须拒绝该回答并进入降级路径，禁止输出不可追溯强断言

#### 场景:引用编号可交互映射
- **当** 回答文本包含 `[n]` 引用标记
- **那么** 系统输出必须能让 UI 将 `[n]` 映射到第 n 条 citation 或等价稳定索引
