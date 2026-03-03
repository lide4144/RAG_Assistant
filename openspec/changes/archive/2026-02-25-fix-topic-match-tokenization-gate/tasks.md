## 1. 主题匹配分词修复

- [x] 1.1 调整主题匹配分词逻辑，支持中英/数字/中文边界切分，覆盖 `Transformer是什么` 类输入
- [x] 1.2 保持现有 stopword 与过滤约束，避免引入无意义 token 噪声
- [x] 1.3 增加分词单元测试，覆盖无空格中英混写、有标点与无标点等变体

## 2. Sufficiency Gate 判定稳健化

- [x] 2.1 在 Gate 中分别计算 `standalone_query` 与 `query_used(calibrated_query)` 的主题匹配分数
- [x] 2.2 引入稳健聚合分数并用于 `topic_mismatch` 判定，避免单路径异常导致误拒
- [x] 2.3 在 run trace 中落盘双路径分数与聚合分数字段，保证可诊断

## 3. 拒答来源一致性

- [x] 3.1 增加最终拒答来源字段（如 `final_refuse_source`），区分 Sufficiency Gate 与 Evidence Policy Gate
- [x] 3.2 调整弱回答模板文案生成逻辑，使文案与真实拒答来源一致
- [x] 3.3 增加来源一致性测试，验证 `decision/reason/source` 与最终文案不冲突

## 4. 回归验证与验收

- [x] 4.1 复现并验证 `runs/20260225_005845` 类场景，不再因 `topic_match_score=0` 误触发 `topic_mismatch`
- [x] 4.2 执行库外问题回归，确认拒答能力保持（`refuse/clarify`）
- [x] 4.3 更新验收记录，明确改动前后行为差异与已知限制

## 5. 验收记录

- [x] 5.1 历史误拒场景对比：`runs/20260225_005845`（改动前）中 `sufficiency_gate.topic_match_score=0.0` 且 `decision=refuse`；`runs/20260225_012420`（改动后）中 `topic_match_score_standalone=0.5`、`topic_match_score_query_used=1.0`、`topic_match_score_robust=1.0`，`decision=answer`
- [x] 5.2 库外问题回归：`venv/bin/python -m pytest tests/test_m8_sufficiency_gate.py::SufficiencyGateUnitTests::test_out_of_corpus_10_questions_not_answer -q` 通过（10/10 不进入 `answer`）
- [x] 5.3 影响回归：`venv/bin/python -m pytest tests/test_m8_sufficiency_gate.py tests/test_m7_evidence_policy.py tests/test_m2_retrieval_qa.py tests/test_runlog_and_config.py -q` 通过（62 passed）
- [x] 5.4 已知限制：稳健聚合当前采用 `max(standalone, query_used)`；当两条路径都被噪声干扰时，仍可能出现 topic 误判，后续可评估加权聚合或最小覆盖约束
