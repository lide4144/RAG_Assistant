## 1. Planner Runtime 重定义

- [x] 1.1 盘点并重命名现有 `app/planner_shell.py`、`app/capability_planner.py` 与相关 trace 字段中的“shell / planner”语义，使代码与文档统一指向顶层 `LLM Planner runtime`
- [x] 1.2 固化 planner runtime 的统一 state schema，补齐 planner 决策、tool 调用、fallback、response 等顶层字段，并明确哪些字段属于可扩展 envelope、哪些字段属于稳定契约
- [x] 1.3 将 runtime 的顶层入口、路由节点与 legacy fallback 路径整理为单一真相源，避免 `qa.py`、Gateway 或其他旁路继续承担顶层理解职责

## 2. Tool 与 Kernel 边界收口

- [x] 2.1 为 planner runtime 定义最小可用的 tool contract，覆盖结构化输入、结构化输出、失败原因、依赖产物与可观测元数据
- [x] 2.2 将现有 catalog、summary、fact QA、control 和研究辅助相关能力映射为“runtime 可调用能力”边界，先明确 contract 和 adapter，不直接重写具体 tool 实现
- [x] 2.3 明确 kernel 在 agent-first 架构中的稳定职责，确保 evidence gate、citation、任务状态、trace 落盘和确定性 pipeline 仍由 kernel 持有

## 3. 回退与安全边界

- [x] 3.1 实现 planner fallback 与 tool/pipeline fallback 的区分记录和停止规则，确保两类降级都能在 trace 中被明确审计
- [x] 3.2 为 planner runtime 增加未注册 tool、超步数计划、空依赖结果和证据不足场景下的硬性 guardrails，禁止无边界自治重试
- [x] 3.3 校验研究辅助/论文助理类输出仍通过 kernel 的 evidence 与 citation 约束，不允许高层能力绕过安全边界直接输出

## 4. Gateway 与兼容迁移

- [x] 4.1 保持 Gateway 仅承担协议入口和兼容回退职责，移除或禁止新增 Node 侧 capability taxonomy、tool 语义判断和 planner 复制逻辑
- [x] 4.2 验证 `Local` 请求持续以 planner runtime 为唯一顶层后端入口，同时 `Web`、`Hybrid` 和 legacy `/qa*` 保持兼容回退能力
- [x] 4.3 更新相关实现说明、OpenSpec 引用和迁移文档，使后续 `tool selection`、`kernel tools`、`agent observability` 等变更默认以本 runtime 边界为前提

## 5. 验证与回归

- [x] 5.1 为 planner runtime 增加覆盖顶层 state、tool envelope、fallback 分类和 guardrail 行为的单元测试
- [x] 5.2 为 kernel / gateway 链路增加集成测试，覆盖 planner runtime 正常执行、runtime 不可用回退、tool 失败停止和标准事件协议保持不变
- [x] 5.3 复核 `paper-assistant-mode` 在 agent-first 路线下的行为，确认研究辅助请求经过 planner 调度、最小澄清和可追溯输出约束
