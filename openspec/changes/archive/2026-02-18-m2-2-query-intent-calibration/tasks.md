## 1. Intent Calibration 核心能力

- [x] 1.1 在检索编排路径新增 `calibrate_query_intent`（输入 Q、rewritten_query、keywords_entities，输出 calibrated_query 与 calibration_reason）
- [x] 1.2 实现规则 A：scope 歧义且无 paper clue 时，移除/禁止 summary cue words（summary/overview/abstract/reporting）
- [x] 1.3 实现规则 B：limitation/contribution/dataset/metric（可选 architecture）意图命中与中英文 cue words 追加
- [x] 1.4 将最终检索查询切换为 `calibrated_query` 并保持与 M3 rewrite 模块解耦

## 2. Shell 检测与单次 Retry

- [x] 2.1 实现 Top-5 evidence summary shell 检测器（覆盖 In summary、SUMMARY OF、Reporting summary 等模式）
- [x] 2.2 实现触发条件：shell 占比 > 60% 且 `query_retry_used=false`
- [x] 2.3 实现最多一次 retry：移除 shell cues、强制追加意图 cues、重跑检索并记录 retry 原因

## 3. 输出与日志字段

- [x] 3.1 扩展 QA 输出/runs 字段：`calibrated_query`、`calibration_reason`、`query_retry_used`、`query_retry_reason`
- [x] 3.2 更新日志 schema 校验，确保上述字段缺失时可被检测
- [x] 3.3 为关键 intent_calibration 接口补充中文 docstring

## 4. 测试与评估

- [x] 4.1 增加单元测试：意图匹配、summary cue 禁用、retry 触发与一次上限
- [x] 4.2 增加集成测试：歧义问题下 Top-5 shell 比例下降且 evidence 不被 summary shell 主导
- [x] 4.3 生成 `reports/m2_2_intent_calibration.md`（>=10 条记录：Q/rewritten/calibrated/retry/Top-5/shell 占比）
