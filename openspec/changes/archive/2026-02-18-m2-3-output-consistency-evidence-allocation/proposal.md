## 为什么

当前 M2.1/M2.2 的 QA 输出在论文排名、证据分组与回答引用之间存在不一致，导致结果可解释性和可复现性不足。现在需要在不改动 M2 检索内核与 M3 rewrite 模块的前提下，补齐输出一致性和证据分配策略，防止“有结论无证据”或“有排名无证据”的情况。

## 变更内容

- 规范化 QA 输出结构，新增 `answer_citations` 与 `output_warnings`，并统一 `question/mode/scope_mode/query_used/rewrite_rule_query/calibrated_query/papers_ranked/evidence_grouped/answer` 字段约束。
- 引入 `papers_ranked` 与 `evidence_grouped` 的一致性修复规则，确保 Top-N 论文均有可展示 evidence，必要时自动补证据并记录 warning。
- 固化 evidence 分配策略：限制每篇论文 evidence 数量、限制展示论文数量、保证 quote 来源与长度约束。
- 增加 scope-aware Answer 规则：`rewrite_scope` 必须输出跨论文聚合式回答并带可追溯 citations；`open` 在显式单论文线索下允许单论文回答。
- 增加证据不足降级模板与 warning 机制，避免无依据生成结论。
- 继承并强化 M2.2 summary shell 抑制结果，在仍被 shell 主导时输出显式 warning。

## 功能 (Capabilities)

### 新增功能
- `output-consistency-evidence-allocation`: 约束 QA 最终输出的一致性、证据分配与引用追踪，覆盖 answer/evidence/paper 三者对齐规则。

### 修改功能
- `rag-baseline-retrieval`: 增加 M2.3 的输出字段与一致性规则，补充 answer 生成与 evidence 选择的强约束。
- `multi-paper-scope-policy`: 扩展 scope_mode 下的回答结构与 citation 对齐要求，补充 rewrite_scope/open 模式差异化输出规范。
- `pipeline-development-conventions`: 扩展运行日志字段约束（含新增输出字段与 warning）以保证复现。

## 影响

- 受影响代码：`app/qa.py`、`app/retrieve.py`（如需补充分配辅助逻辑）、可能新增 `app/output_policy.py` 或同类模块。
- 受影响测试：`tests/test_m2_retrieval_qa.py` 及新增一致性/降级/citation 对齐测试。
- 受影响报告：新增并维护 `reports/m2_3_output_consistency.md`。
- 对外接口影响：QA JSON 输出字段扩充（向后兼容读取逻辑需确认）。
