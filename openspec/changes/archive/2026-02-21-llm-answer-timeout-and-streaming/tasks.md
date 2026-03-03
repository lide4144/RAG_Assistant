## 1. 配置与调用基础

- [x] 1.1 在 `app/config.py` 与 `configs/default.yaml` 增加回答流式开关与回答阶段专用超时配置（并保持对 `llm_timeout_ms` 的兼容）
- [x] 1.2 在配置校验中加入新字段合法性检查与默认值回填，确保旧配置不报错
- [x] 1.3 在 `app/llm_client.py` 增加回答流式调用接口，并统一归一化 timeout/断流/空流/解析失败错误类型

## 2. 回答阶段流式实现

- [x] 2.1 在 `app/qa.py` 的 `llm_answer_with_evidence` 路径接入流式调用（受 `answer_stream_enabled` 控制）
- [x] 2.2 实现流式内容累积与结束后结构化解析，确保继续输出 `answer` 与 `answer_citations`
- [x] 2.3 保持 citation 子集校验与 evidence policy gate 行为不变，流式路径不允许绕过
- [x] 2.4 对首字超时、流式中断、空流、非法结构化结果统一回退模板回答并追加标准 warning

## 3. 输出与诊断一致性

- [x] 3.1 扩展 run trace/qa report 输出字段，记录流式启用、是否实际走流、首字延迟或回退原因
- [x] 3.2 更新 `app/runlog.py` schema 校验，保证新增流式字段类型与 warning/diagnostics 语义一致
- [x] 3.3 确保 `answer_llm_diagnostics` 在流式失败场景下完整落盘且不泄露敏感信息

## 4. 测试与回归

- [x] 4.1 扩展 `tests/test_m2_retrieval_qa.py`：覆盖流式成功、流式超时、流式中断、流式解析失败降级
- [x] 4.2 扩展 `tests/test_runlog_and_config.py`：覆盖新配置与流式输出字段校验
- [x] 4.3 回归 `tests/test_m7_evidence_policy.py` 与既有 answer/rewrite 测试，确认证据门控与 fallback 语义不回退
- [x] 4.4 生成评估记录（至少包含高 evidence 负载场景）并补充到对应 `reports/` 文档

## 5. CLI 实时流式可见性

- [x] 5.1 在 `app/qa.py` CLI 输出路径实现流式增量显示（而非仅最终一次性打印）
- [x] 5.2 保持流式显示与结构化校验/证据门控解耦，确保失败场景仍按现有 fallback 语义收敛
- [x] 5.3 扩展 `tests/test_m2_retrieval_qa.py` 覆盖 CLI 流式输出行为（包含成功与中断/回退）
