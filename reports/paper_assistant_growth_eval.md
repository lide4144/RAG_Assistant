# Paper Assistant Growth Eval

## 输入
- 问题集: `reports/paper_assistant_questions_v1.jsonl`
- 旧策略配置: `configs/paper_assistant_growth_legacy.yaml`
- 新策略配置: `configs/paper_assistant_growth.yaml`

## 总体对比

| 指标 | 旧策略 | 新策略 | 变化 |
|---|---:|---:|---:|
| refuse_rate | 0.0% | 0.0% | 0.0% |
| clarify_rate | 0.0% | 0.0% | 0.0% |
| answer_with_citation_rate | 0.0% | 0.0% | 0.0% |

## 分桶结果

| Bucket | Strategy | total | refuse | clarify | answer+citation |
|---|---|---:|---:|---:|---:|
| A_open_summary | legacy | 0 | 0.0% | 0.0% | 0.0% |
| A_open_summary | growth | 0 | 0.0% | 0.0% | 0.0% |
| B_multi_turn | legacy | 0 | 0.0% | 0.0% | 0.0% |
| B_multi_turn | growth | 0 | 0.0% | 0.0% | 0.0% |
| C_control_mixed | legacy | 0 | 0.0% | 0.0% | 0.0% |
| C_control_mixed | growth | 0 | 0.0% | 0.0% | 0.0% |
| D_ooc | legacy | 0 | 0.0% | 0.0% | 0.0% |
| D_ooc | growth | 0 | 0.0% | 0.0% | 0.0% |

## 配置一致性
- PASS

## 发布门禁
- 结果: FAIL
- 不通过项:
- A_open_summary answer_with_citation_rate below growth threshold
- A_open_summary refuse_rate above growth threshold
- B_multi_turn chain_has_answer_with_citation_in_two_rate below threshold
- B_multi_turn max_consecutive_clarify exceeds threshold
- B_multi_turn third_turn_force_answer_rate below threshold
- C_control_mixed control_misroute_rate above threshold
- C_control_mixed control_recovery_rate below threshold
- D_ooc answer_rate above threshold
- D_ooc unsafe_ooc_answer_rate above threshold
- hard guard no_citation_answer_rate above threshold
- delta answer_with_citation_rate improvement below threshold
- delta refuse_rate reduction below threshold

## 回滚建议
- 建议将 `assistant_mode_force_legacy_gate=true` 作为临时回滚。
