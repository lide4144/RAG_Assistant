## 为什么

当前 `paper-assistant-friendly-mode` 已显著改善体验，但发布判断主要依赖一次性汇总报告，缺少可复现的问题集与统一计分口径。为了支撑增长目标，需要把“增长优先”的评测与门槛固化为可持续执行的发布规约。

## 变更内容

- 新增固定口语问题集规范（分桶、字段、样本规模、版本化管理）。
- 新增双策略对比评测规范：同问题集下比较 `assistant_mode_force_legacy_gate=true/false`。
- 统一发布计分口径：仅使用 `qa_report.decision`，并要求按桶统计（首问、多轮、控制混入、语料外）。
- 将发布门槛升级为“增长优先”版本：优先提升可追溯回答率，同时保留误答与连续澄清护栏。
- 明确灰度放量与回滚触发条件，避免人工解释歧义。

## 功能 (Capabilities)

### 新增功能
- `paper-assistant-growth-evaluation`: 定义增长优先评测协议、问题集结构、分桶指标与放行规则。

### 修改功能
- `paper-assistant-mode`: 将发布门槛从静态汇总升级为可复现的增长优先门槛，并补充灰度/回滚规则。
- `sufficiency-gate`: 明确增长模式下连续澄清与强制降级回答的统计与验收口径。

## 影响

- 受影响规格：新增 `paper-assistant-growth-evaluation`，并更新 `paper-assistant-mode`、`sufficiency-gate` 增量规范。
- 受影响实现（后续 apply 阶段）：评测脚本、问题集文件、报告生成流程、发布检查脚本。
- 受影响产物：`reports/paper_assistant_*` 系列报告与对应运行统计。
