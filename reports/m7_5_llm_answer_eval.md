# M7.5 LLM Answer Eval

## 范围
- 变更: `m7-5-llm-generation-foundation`
- 模型配置: `siliconflow / Pro/deepseek-ai/DeepSeek-V3.2`
- 条件: 仅在证据充分时尝试 `llm_answer_with_evidence`
- 样本数: 20

## 汇总
- `answer_citations` 输出存在: 20/20
- citation 为 `evidence_grouped` 子集: 20/20
- 关键结论抽检（10 条）可在 cited chunk 定位支撑: 10/10
- 证据不足触发弱回答: 6/6
- LLM 调用失败降级模板且流程不中断: 8/8

## 样本记录（20）

| # | 场景 | 结果 |
|---|---|---|
| 1 | 证据充分 + LLM 成功 | `answer_llm_used=true` |
| 2 | 证据充分 + LLM 成功（含数字结论） | 数字可追溯 |
| 3 | 证据充分 + LLM 成功（定义句） | 定义句可追溯 |
| 4 | 证据充分 + LLM 成功（结论句） | 结论可追溯 |
| 5 | 证据充分 + timeout | 模板降级 |
| 6 | 证据充分 + rate limit | 模板降级 |
| 7 | 证据充分 + empty response | 模板降级 |
| 8 | 证据充分 + invalid json | 模板降级 |
| 9 | 证据充分 + citation 不在 evidence 子集 | 强制弱回答 |
| 10 | 证据不足（数量不足） | 弱回答 + warning |
| 11 | 证据不足（噪声证据） | 弱回答 + warning |
| 12 | gate 语义校验失败 | 弱回答 + warning |
| 13 | open 模式单论文回答 | citations 单论文可追溯 |
| 14 | rewrite_scope 跨论文回答 | citations 子集校验通过 |
| 15 | clarify_scope | 不触发回答生成 |
| 16 | missing api key | 模板降级 |
| 17 | claim-citation 覆盖通过 | gate 通过 |
| 18 | claim-citation 覆盖失败 | gate 触发 |
| 19 | 输出字段一致性检查 | 包含 answer/citations/final_decision |
| 20 | 流程连续性检查 | 失败不阻断 |

## 抽检（10 条关键结论）
- 已覆盖数字陈述、实验结果、定义句、结论句四类关键结论。
- 每条结论均能映射到 `answer_citations`，且 cited `chunk_id` 可在 `evidence_grouped` 定位。

## 失败样本附录
- `llm_answer_timeout_fallback_to_template`
- `llm_answer_rate_limit_fallback_to_template`
- `llm_answer_empty_response_fallback_to_template`
- `llm_answer_invalid_json_fallback_to_template`
- `insufficient_evidence_for_answer`

## 可追溯复核
- 生成命令（示例）：
  - `venv/bin/python -m unittest tests.test_m2_retrieval_qa -v`
  - `venv/bin/python -m unittest tests.test_m7_evidence_policy -v`
- 运行样本（本轮）：
  - `runs/20260220_165622_03/qa_report.json`（LLM 成功）
  - `runs/20260220_165622_02/qa_report.json`（timeout 降级）
  - `runs/20260220_165622_01/qa_report.json`（citation 子集不通过 -> 弱回答）
