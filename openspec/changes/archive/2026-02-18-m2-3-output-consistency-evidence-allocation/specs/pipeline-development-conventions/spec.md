## 修改需求

### 需求:运行日志字段完整性
系统在 M2.2 QA 运行中必须额外记录 `calibrated_query`、`calibration_reason`、`query_retry_used`、`query_retry_reason`。系统还必须记录本次校准命中的意图类别与追加 cue words（可包含在 `calibration_reason` 中）。

#### 场景:M2.2 运行记录校准与重试
- **当** 用户执行带意图校准的 QA 检索
- **那么** runs JSON 必须完整记录校准字段、重试开关与重试原因（若触发）

## 新增需求

### 需求:M2.3 输出一致性日志记录
系统在 M2.3 QA 运行中必须记录 `answer_citations` 与 `output_warnings`，并确保 warning 可用于回放异常修复过程（例如 top_paper 补证据、证据不足降级、summary shell 仍主导）。

#### 场景:M2.3 输出治理字段落盘
- **当** QA 流程完成回答输出
- **那么** 对应 runs JSON 必须落盘 citation 与 warning 字段，且字段可用于复现本次输出决策

### 需求:M2.3 评估记录
系统必须生成 `reports/m2_3_output_consistency.md`，至少记录 10 条问题的 `Q`、`scope_mode`、`calibrated_query`、`papers_ranked(top5)`、`evidence_grouped`、`answer`、`answer_citations`、`output_warnings`，并包含 3 个 M2.2 与 M2.3 的对比案例。

#### 场景:完成 M2.3 评估后落盘
- **当** 用户完成 M2.3 问题集评估
- **那么** 系统必须在 `reports/m2_3_output_consistency.md` 写入不少于 10 条记录与 3 条对比案例
