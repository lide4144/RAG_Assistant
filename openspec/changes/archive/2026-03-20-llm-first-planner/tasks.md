## 1. 规范与决策面收口

- [x] 1.1 更新 planner runtime、tool selection、decision validation、control intent 和 interaction authority 对应实现/配置常量，使线上正式模式只保留 LLM-first 主决策语义
- [x] 1.2 移除或停用 `rule_only`、`llm_primary_with_rule_fallback` 等线上正式模式入口，并明确 `rule planner` 仅用于离线诊断或历史回放
- [x] 1.3 收敛顶层 `decision_result` 枚举与失败语义，将线上正式回退从 `legacy_fallback` 改为受控结束语义

## 2. Planner 与 Validation 运行时改造

- [x] 2.1 调整 planner runtime，只接受通过 validation 的 `LLM planner decision` 进入正式执行链
- [x] 2.2 修改 validation gate 与相关分支逻辑，使 reject 不再切换到 `rule planner`，而是产出稳定的 rejection reason、layer 和受控结束类型
- [x] 2.3 更新多轮关系、控制意图和能力选择入口，使正式执行链中的这些解释结果统一来自 `LLM planner decision`
- [x] 2.4 收紧 tool registry 解析与执行前校验，确保非法 action、未注册能力和缺失依赖都进入受控结束而不是旧规则路径

## 3. 失败收束与可观测性

- [x] 3.1 为 planner reject、tool/constraint failure 和 runtime exception 建立统一的受控结束状态对象与用户可见姿态映射
- [x] 3.2 扩展 trace / observability 字段，记录 `interaction_decision_source`、`final_interaction_authority`、`rejection_reason`、`rejection_layer`、失败收束来源与 `posture_override_forbidden`
- [x] 3.3 增加保护逻辑，阻止 `rule planner`、`legacy QA`、`sufficiency gate` 或其他尾部规则在失败时改写最终用户姿态
- [x] 3.4 将 `rule planner` 的 shadow / 对比能力隔离到离线诊断或非主链记录路径，确保其不能接管线上正式回答

## 4. 验证与回归

- [x] 4.1 为 validation reject、非法 tool、缺失字段、策略拒绝和 runtime exception 补充测试，验证系统进入受控结束且不触发规则回退
- [x] 4.2 为多轮关系判断、控制意图解释和顶层路径选择补充测试，验证正式结果来自 `LLM planner decision` 而不是独立规则链
- [x] 4.3 为最终交互姿态和 trace 字段补充测试，验证失败收束时仍由 planner/policy 决定最终姿态且无 legacy tail override
- [x] 4.4 清理或标记不再适用的旧规则回退测试、文档与配置说明，确保仓库内不再把 `rule planner` 描述为线上正式兜底路径
