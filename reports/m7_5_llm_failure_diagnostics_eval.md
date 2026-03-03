# M7.5 LLM Failure Diagnostics Eval

## 范围
- 变更: `llm-failure-diagnostic-logging`
- 目标: 验证 rewrite/answer 失败时是否输出结构化诊断对象，并与 `output_warnings` 一致。
- 运行方式: `venv/bin/python -m unittest` 定向失败路径用例。

## 诊断字段检查
- 诊断对象字段: `stage`、`provider`、`model`、`reason`、`status_code`、`attempts_used`、`max_retries`、`elapsed_ms`、`fallback_warning`、`timestamp`。
- 敏感信息检查: 未在诊断对象中写入 API key、完整 prompt、完整 response body。
- 兼容性检查: 历史 run（无 diagnostics 字段）仍可通过 `validate_trace_schema`。

## 失败类型分布（本轮定向验证）

| 失败类型 | 阶段 | warning | 次数 |
|---|---|---|---|
| timeout | answer | `llm_answer_timeout_fallback_to_template` | 1 |
| fallback_disabled | answer | `llm_fallback_disabled_skip_llm_answer` | 1 |
| missing_api_key | rewrite | `llm_missing_api_key_fallback_to_rules` | 1 |

## 样例
- answer timeout:
  - `runs/20260220_225201_01/qa_report.json`
  - 关键字段: `answer_llm_diagnostics.stage=answer`, `reason=timeout`, `fallback_warning=llm_answer_timeout_fallback_to_template`
- answer fallback disabled:
  - `runs/20260220_225201_02/qa_report.json`
  - 关键字段: `answer_llm_diagnostics.reason=fallback_disabled`
- rewrite missing api key:
  - `runs/20260220_225201/qa_report.json`
  - 关键字段: `rewrite_llm_diagnostics.stage=rewrite`, `reason=missing_api_key`

## 验证命令
- `venv/bin/python -m unittest tests.test_rewrite.RewriteTests.test_llm_optional_flag_falls_back_when_enabled`
- `venv/bin/python -m unittest tests.test_rewrite.RewriteTests.test_llm_rewrite_timeout_falls_back`
- `venv/bin/python -m unittest tests.test_runlog_and_config.RunlogTests.test_validate_trace_schema_accepts_m2_optional_fields`
- `venv/bin/python -m unittest tests.test_m2_retrieval_qa.M2RetrievalQATests.test_rewrite_llm_missing_key_records_diagnostics_and_warning`
- `venv/bin/python -m unittest tests.test_m2_retrieval_qa.M2RetrievalQATests.test_llm_answer_timeout_falls_back_to_template`
- `venv/bin/python -m unittest tests.test_m2_retrieval_qa.M2RetrievalQATests.test_llm_fallback_disabled_skips_llm_answer_attempt`
