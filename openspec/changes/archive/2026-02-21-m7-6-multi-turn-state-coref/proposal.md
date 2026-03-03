## 为什么

当前流水线以单轮检索为主，连续追问时容易出现上下文膨胀与指代丢失，导致检索意图漂移、澄清流程断裂，以及成本上升。M7.6 需要补齐基于 session 的多轮状态闭环，在低 token 开销下提升多轮稳定性与抗幻觉能力。

## 变更内容

- 新增基于 `session_id` 的会话状态存储与读取机制，按“证据脱水”策略仅保存 User 问题、AI 最终答案、引用 `chunk_id` 与决策信息。
- 在重写阶段引入滑动窗口历史（默认最近 3 轮）进行指代消解，生成 `standalone_query`，禁止把历史整段回答拼接进查询。
- 增加 Clarify 状态闭环：当上一轮决策为 `clarify` 时，本轮先执行“上一轮原始问题 + 澄清问题 + 用户补充”的强制合并，再进入检索链路。
- 增加会话隔离与手动清空接口 `clear_session(session_id)`，防止跨主题污染。
- 扩展运行日志字段：`session_id`、`turn_number`、`history_used_turns`、`history_tokens_est`、`coreference_resolved`、`standalone_query`。
- 新增评估报告 `reports/m7_6_multi_turn_cases.md`，记录多组多轮样例与 token 增长趋势。

## 功能 (Capabilities)

### 新增功能
- `multi-turn-session-state`: 基于 session 的多轮状态机、证据脱水存储、clarify 闭环与会话清空能力。

### 修改功能
- `query-rewriting`: 增加多轮历史驱动的指代消解与 `standalone_query` 产出约束。
- `multi-paper-scope-policy`: 增加 clarify 决策后的下一轮强制合并流转规则，避免死循环。

## 影响

- 受影响代码：`app/qa.py`、`app/runlog.py`、新增 `app/session_state.py`。
- 测试影响：新增多轮状态机测试与 runlog 字段校验更新。
- 日志与报告影响：`run_trace.json` / `qa_report.json` 字段扩展，新增 M7.6 评估报告。
