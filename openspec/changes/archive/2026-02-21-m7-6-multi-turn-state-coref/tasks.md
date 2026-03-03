## 1. 会话状态基础

- [x] 1.1 新增 `app/session_state.py`，实现 session 读写、滑动窗口加载、token 估算与实体提取
- [x] 1.2 实现 `clear_session(session_id)` 接口并保证会话隔离
- [x] 1.3 实现 clarify pending 合并逻辑与独立查询生成入口

## 2. QA 链路接入

- [x] 2.1 在 `app/qa.py` 增加 `--session-id`、`--session-store`、`--clear-session` 参数
- [x] 2.2 在 rewrite 前接入历史窗口与指代消解，产出 `standalone_query`
- [x] 2.3 接入 clarify 闭环：上一轮澄清后本轮强制 merge 再检索
- [x] 2.4 在 answer 阶段仅注入简短历史前情作为语气上下文，事实仍仅来自当轮证据

## 3. 日志与校验

- [x] 3.1 在 trace/report 中新增 `session_id`、`turn_number`、`history_used_turns`、`history_tokens_est`、`coreference_resolved`、`standalone_query`
- [x] 3.2 更新 `app/runlog.py` 的 schema 校验以覆盖新增字段
- [x] 3.3 保持旧调用兼容：`run_qa` 对新增参数使用默认回退

## 4. 测试与评估

- [x] 4.1 新增 `tests/test_m7_6_multi_turn.py`，覆盖 coref、clarify 闭环、clear_session、脱水存储
- [x] 4.2 更新 `tests/test_runlog_and_config.py` 以验证新增日志字段
- [x] 4.3 运行回归测试（含 `tests.test_m2_retrieval_qa`）并修复兼容性问题
- [x] 4.4 产出 `reports/m7_6_multi_turn_cases.md`，记录 5 组多轮样例与 token 增长趋势
