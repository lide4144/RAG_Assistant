## 修改需求

### 需求:运行日志字段完整性
系统在 M2.2 QA 运行中必须额外记录 `calibrated_query`、`calibration_reason`、`query_retry_used`、`query_retry_reason`。系统还必须记录本次校准命中的意图类别与追加 cue words（可包含在 `calibration_reason` 中）。

#### 场景:M2.2 运行记录校准与重试
- **当** 用户执行带意图校准的 QA 检索
- **那么** runs JSON 必须完整记录校准字段、重试开关与重试原因（若触发）

## 新增需求

### 需求:M2.2 评估记录
系统必须生成 `reports/m2_2_intent_calibration.md`，至少记录 10 条问题的 `Q`、`rewritten_query`、`calibrated_query`、是否 retry、Top-5 evidence 与 summary shell 占比统计。

#### 场景:完成 M2.2 评估后落盘
- **当** 用户完成 M2.2 问题集评估
- **那么** 系统必须在 `reports/m2_2_intent_calibration.md` 写入不少于 10 条记录并可复现校准行为
