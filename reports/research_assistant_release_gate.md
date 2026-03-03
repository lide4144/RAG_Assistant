# Research Assistant Release Gate

## 发布门槛

- 任务完成率门槛：`completion_rate >= 0.70`
- 首张卡片时间门槛：`avg_first_card_seconds <= 120`
- 引用可追溯门槛：抽样 20 条回答中，引用可点击并展示证据来源通过率 `>= 95%`
- 稳定性门槛：核心回归测试全部通过（UI、会话、Sufficiency、run_trace schema）

## 失败回退策略

1. 将 `UI_LEGACY_LAYOUT=1` 或配置 `ui_legacy_layout_default: true`，切回旧默认布局。
2. 保留新数据结构（Ideas、topic scope）但隐藏入口，仅保留调试台工作流。
3. 记录失败会话事件并重新评估：导入反馈、引用可读性、卡片保存路径。
4. 仅在上述门槛重新达标后恢复新默认布局。
