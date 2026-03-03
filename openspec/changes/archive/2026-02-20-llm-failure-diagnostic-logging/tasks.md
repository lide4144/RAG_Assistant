## 1. LLM 诊断模型与字段扩展

- [x] 1.1 扩展 `app/llm_client.py` 的返回结构，增加失败诊断所需字段（阶段外元数据、状态码、重试次数、耗时、统一 reason）。
- [x] 1.2 在 `app/rewrite.py` 接入 rewrite 阶段诊断对象生成，并与现有 fallback warning 对齐。
- [x] 1.3 在 `app/qa.py` 接入 answer 阶段诊断对象生成，并与现有 fallback warning 对齐。

## 2. 运行产物落盘与 Schema 校验

- [x] 2.1 在 `run_trace.json` 中新增 rewrite/answer 失败诊断字段，保证失败时可追踪、成功时向后兼容。
- [x] 2.2 在 `qa_report.json` 中新增 rewrite/answer 失败诊断字段，确保输出结构可序列化。
- [x] 2.3 更新 `app/runlog.py` 校验规则，校验新增字段类型与 warning-诊断一致性约束。

## 3. 安全与兼容约束

- [x] 3.1 增加敏感信息保护逻辑，确保诊断日志不包含 API key、完整 prompt、完整响应正文。
- [x] 3.2 验证老 run 产物与新字段共存，确认新增字段可空且不破坏现有读取流程。

## 4. 验证与验收

- [x] 4.1 构造 answer timeout、rewrite rate_limit、HTTP 错误、解析失败、缺失 API key 等路径并验证诊断字段落盘。
- [x] 4.2 验证 `output_warnings` 与诊断对象 `reason/stage` 一致（含 `llm_answer_timeout_fallback_to_template`、`llm_timeout_fallback_to_rules` 等）。
- [x] 4.3 更新或新增评估报告片段，记录失败类型分布与样例，确保变更可审计。
