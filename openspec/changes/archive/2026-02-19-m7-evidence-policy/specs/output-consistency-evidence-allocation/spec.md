## ADDED Requirements

### 需求:M7 验收检查必须可执行
系统必须提供可执行的 M7 验收检查流程：
1) 对 30 个问题运行自动检查，要求回答输出均包含 citations；
2) 对 10 个回答提供抽检材料，能从被引用 chunk 中找到语义一致支撑。

#### 场景:自动检查 30 题引用完整
- **当** 执行 M7 自动验收脚本并输入 30 个问题集
- **那么** 脚本结果必须显示 30/30 回答包含 citations，且失败样例必须输出问题与缺失字段详情

#### 场景:人工抽检 10 条可追溯
- **当** 执行抽检导出流程并随机抽取 10 条回答
- **那么** 系统必须输出每条回答的关键结论、citation 与对应 chunk 片段，支持人工核验语义一致性

## MODIFIED Requirements

### 需求:回答引用可追溯
系统必须输出 `answer_citations=list[{chunk_id, paper_id, section_page}]`，并保证每条关键结论均至少对应 1 条 citation。每条 citation 必须对应 `evidence_grouped` 内已展示证据，且关键结论中的数字、实验结果、定义句必须能在对应 chunk 中找到语义一致支撑。

#### 场景:citation 与关键结论对齐
- **当** 回答包含关键结论（含数字、实验结果、定义句）
- **那么** 系统必须为每条关键结论输出 citation，且 citation 的 `chunk_id` 必须可在 `evidence_grouped` 找到

#### 场景:关键结论无法被证据支撑
- **当** 关键结论对应 citation 缺失或在引用 chunk 中无法找到语义一致支撑
- **那么** 系统必须拒绝输出该强断言，并转入证据不足降级路径

### 需求:证据不足降级
当证据总量不足、证据质量不足或关键结论追溯校验失败时，系统必须使用弱回答模板并提示补充线索，禁止生成具体编造结论，同时在 `output_warnings` 中增加 `insufficient_evidence_for_answer`。

#### 场景:证据不足触发降级
- **当** evidence 总数小于 2 或 evidence 为空，或 evidence 全为高噪声类型
- **那么** 系统必须输出弱回答模板并记录 `insufficient_evidence_for_answer`

#### 场景:追溯校验失败触发降级
- **当** 任一关键结论未通过“citation 可定位 + 语义一致”校验
- **那么** 系统必须触发弱回答降级并记录 `insufficient_evidence_for_answer`

## REMOVED Requirements
