## 1. Planner Policy Schema

- [x] 1.1 定义顶层 `planner decision` 数据结构，补齐 `decision_result`、`knowledge_route`、`research_mode`、`selected_tools_or_skills`、`action_plan`、`fallback` 等稳定字段
- [x] 1.2 梳理 planner 最小输入 contract，明确 `request`、`conversation_context`、`capability_registry` 与 `policy_flags` 的来源和边界
- [x] 1.3 约束 `decision_result` 的有限枚举与步数上限，禁止未注册顶层结果和无限步 planning

## 2. Registry And Routing

- [x] 2.1 定义 planner 可消费的 tool/skill registry 最小元数据，覆盖名称、类型、能力标签、知识范围和前置条件
- [x] 2.2 调整 runtime 路由逻辑，使其按标准化 `planner decision` 区分 `clarify`、`local_execute`、`delegate_web`、`delegate_research_assistant` 与 `legacy_fallback`
- [x] 2.3 保持联网路径为委托语义，只定义何时委托到既有 `Web/Hybrid` 链路，不重写 gateway 协议或 kernel 底层联网实现

## 3. Research Assistant And Fallbacks

- [x] 3.1 将论文助理/研究辅助入口改为仅由 `delegate_research_assistant` 决策触发，移除隐式旁路进入方式
- [x] 3.2 在研究辅助前置条件不足时实现统一 `clarify` 停止语义，保证一次仅产生一条澄清问题
- [x] 3.3 明确 planner fallback 与 tool/pipeline fallback 的分类、触发条件与停止规则，禁止 planner 失败后无边界重试

## 4. Observability And Verification

- [x] 4.1 在 trace 中落盘最小 planner 观测字段，包括 `planner_used`、`planner_source`、`decision_result`、`knowledge_route`、`research_mode`、`selected_tools_or_skills`、`planner_fallback` 与 `selected_path`
- [x] 4.2 增加覆盖本地执行、联网委托、研究辅助委托、澄清和 legacy fallback 的 planner/runtime 测试
- [x] 4.3 更新相关设计文档与实现注释，确保后续 `expose-kernel-capabilities-as-agent-tools` 和 `add-agent-observability-and-evals` 复用同一 planner policy 语义
