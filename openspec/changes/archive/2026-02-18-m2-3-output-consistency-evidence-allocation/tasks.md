## 1. 输出治理骨架

- [x] 1.1 在 QA 流程中新增输出治理阶段，统一组装 `papers_ranked`、`evidence_grouped`、`answer`、`answer_citations`、`output_warnings`
- [x] 1.2 扩展 QA 最终输出与 runs 落盘字段，确保包含 `answer_citations` 与 `output_warnings`

## 2. 证据分配与一致性修复

- [x] 2.1 实现按 paper 分组后的证据分配策略（每篇最多 2 条、展示最多 6 篇、展示论文至少 1 条）
- [x] 2.2 实现 `papers_ranked[:5]` 与 `evidence_grouped` 一致性校验与自动修复（Top paper 无证据时补选并写 warning）
- [x] 2.3 实现 quote 生成约束（来源 `text`，长度优先 50~120，不足可短但非空）

## 3. Scope 对齐回答策略

- [x] 3.1 实现 `rewrite_scope` 模式下的跨论文聚合回答模板，禁止单 chunk 指向式回答
- [x] 3.2 实现 `open` 模式单论文回答约束（显式单论文线索下 citation 必须同一 `paper_id`）
- [x] 3.3 实现 `answer_citations` 与 `evidence_grouped` 的双向一致性校验

## 4. 降级与告警策略

- [x] 4.1 实现证据不足判定（数量不足/高噪声主导/无证据）
- [x] 4.2 实现弱回答模板与 `insufficient_evidence_for_answer` 告警
- [x] 4.3 继承 M2.2 summary shell 检测结果，仍主导时写入 `summary_shell_still_dominant`

## 5. 测试与回归保护

- [x] 5.1 新增/更新测试：paper-evidence 一致性、Top paper 自动修复、citation 对齐
- [x] 5.2 新增/更新测试：rewrite_scope/open 回答结构与引用约束
- [x] 5.3 新增/更新测试：证据不足降级与 output_warnings 覆盖

## 6. 评估记录与文档

- [x] 6.1 生成 `reports/m2_3_output_consistency.md`，记录至少 10 条问题全量输出字段
- [x] 6.2 在评估报告中补充至少 3 个 M2.2 vs M2.3 的修复对比案例
