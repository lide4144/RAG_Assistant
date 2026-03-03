## 1. 配置与客户端基础

- [x] 1.1 在 `app/config.py` 与 `configs/default.yaml` 增加 M7.5 配置项：`rewrite_use_llm`、`rewrite_llm_provider`、`rewrite_llm_model`、`answer_use_llm`、`answer_llm_provider`、`answer_llm_model`、`llm_timeout_ms`、`llm_max_retries`、`llm_fallback_enabled`
- [x] 1.2 增加 `SILICONFLOW_API_KEY` 缺失时的配置告警与运行时降级策略（不抛中断错误）
- [x] 1.3 新建统一 `app/llm_client.py`（或等效模块），封装 provider/model/timeout/retry、错误标准化与空响应判定

## 2. Rewrite 阶段改造

- [x] 2.1 在 `app/rewrite.py` 将现有 LLM stub 替换为真实客户端调用，保持“规则先产出、LLM 覆盖、失败回退”顺序
- [x] 2.2 实现 `scope_mode=clarify_scope` 禁用 `llm_rewrite` 的硬约束，并保证 `rewrite_query == rewrite_rule_query`
- [x] 2.3 完善 `rewrite_llm_used`、`rewrite_llm_fallback`、`rewrite_llm_query` 与 `strategy_hits` 的成功/失败原因落盘
- [x] 2.4 增加关键实体保留与“不得引入无关任务目标”的校验逻辑（失败即回退规则改写）

## 3. Answer 阶段改造

- [x] 3.1 在 `app/qa.py` 增加 `llm_answer_with_evidence` 路径：仅在 Sufficiency Gate 充分且 `answer_use_llm=true` 时触发
- [x] 3.2 构建受约束提示：只注入 `question`、`scope_mode`、`evidence_grouped`、`output_warnings`，禁止外部事实补全
- [x] 3.3 为 LLM 回答实现结构化解析与合法性校验（answer + citations），不合法时回退模板回答
- [x] 3.4 强制 `answer_citations` 为 `evidence_grouped` 子集，关键结论缺支撑时触发 `insufficient_evidence_for_answer`
- [x] 3.5 保持 M7 evidence policy gate 二次校验全程生效，LLM 与模板回答共用同一门控逻辑

## 4. 测试与回归

- [x] 4.1 扩展 `tests/test_rewrite.py`：覆盖 LLM 成功、超时/限流/空响应回退、clarify_scope 禁用
- [x] 4.2 扩展 `tests/test_m2_retrieval_qa.py` 与 `tests/test_m7_evidence_policy.py`：覆盖证据充分触发 LLM 回答、失败降级、citation 子集约束
- [x] 4.3 扩展 `tests/test_runlog_and_config.py`：覆盖新增配置字段与运行日志可追踪字段校验
- [x] 4.4 执行 M2~M7 现有回归测试并修复兼容性问题，确保默认配置下行为不回退

## 5. 评估与报告产出

- [x] 5.1 准备至少 20 个问题对比规则改写 vs LLM 改写，统计 `rewrite_llm_used` 与 `rewrite_llm_fallback` 并产出 `reports/m7_5_llm_rewrite_eval.md`
- [x] 5.2 准备至少 20 个问题验证 LLM 回答 citation 完整性，抽检 10 条关键结论可追溯性并产出 `reports/m7_5_llm_answer_eval.md`
- [x] 5.3 记录失败样本（超时/限流/空响应/证据不足）与降级结果，形成可审计附录
