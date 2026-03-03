# paper-assistant-friendly-mode 回归对比

评估日期：2026-02-25  
口径：对同一批“自然提问”样例，比较 `assistant_mode_force_legacy_gate=true`（旧策略）与 `false`（新策略）。

## 数据来源与统计脚本
- 主问题集：`reports/paper_assistant_questions_v1.jsonl`
- 口语问题集：`reports/paper_assistant_questions_spoken_v1.jsonl`
- 统计脚本：`scripts/eval_paper_assistant_growth.py`
- 复现命令：
  - `python scripts/eval_paper_assistant_growth.py --samples reports/paper_assistant_questions_v1.jsonl --spoken-samples reports/paper_assistant_questions_spoken_v1.jsonl --out-md reports/paper_assistant_mode_regression.md --out-json reports/paper_assistant_growth_eval.json`

| 指标 | 旧策略 | 新策略 |
|---|---:|---:|
| 拒答率（decision=refuse） | 40% | 15% |
| 澄清率（decision=clarify） | 35% | 25% |
| 可追溯回答率（answer 且含 citations） | 25% | 60% |

## 样例观察
- 自然首问“总结方向”场景：新策略优先返回主题化总结与建议追问，不再直接 numeric 缺口拒答。
- 多轮追问场景：上一轮澄清约束会在开放式总结意图下被降权，`history_constraint_dropped=true` 可观测。
- 会话清空后场景：`session_reset_audit.constraints_inherited_after_reset=false`。
- 语料外问题：保持 `refuse/clarify`，未出现无证据直接作答。

## 回滚路径
- 关闭助理模式：`assistant_mode_enabled=false`
- 保留助理模式但恢复旧门控：`assistant_mode_force_legacy_gate=true`

## 发布门槛（5.4）

门槛定义：
- 自然首问拒答率（`decision=refuse`）`< 20%`
- 多轮追问链路中，至少 1 轮返回“可追溯主题化回答”（`decision=answer` 且 `answer_citations` 非空）

本次评估结果：
- 自然首问拒答率 = `15%`，满足门槛
- 多轮追问样例中已出现可追溯主题化回答，满足门槛

结论：满足发布门槛，可进入灰度发布；如线上拒答率回升，优先通过 `assistant_mode_force_legacy_gate=true` 快速回退。
