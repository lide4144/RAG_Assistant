## 1. Planner Shell 基础设施

- [x] 1.1 引入 `LangGraph` 依赖并创建 Python 侧 planner shell 模块，定义统一 state、节点接口和入口函数
- [x] 1.2 将现有规则 planner 契约封装进 `plan_chat_request` 节点，确保 state 中稳定写入 `primary_capability`、`strictness`、`action_plan` 与回退标记
- [x] 1.3 实现 `route_capability` 与 `fallback_to_legacy_qa` 节点，优先稳定 `Local` 主聊天问答路径的下一跳规则，并为其他路径预留兼容节点入口

## 2. Kernel 执行接入

- [x] 2.1 先将现有 `Local` 主聊天问答路径封装为 planner shell 可调用节点，保持内部 QA 能力实现不变
- [x] 2.2 为 `catalog`、`summary`、`control` 路径提供兼容节点或 passthrough 接入，复用现有函数或入口而不做同等深度重整
- [x] 2.3 让 planner shell 统一产出 `selected_path`、`execution_trace`、`short_circuit`、`truncated` 等观测字段，并映射到现有 run trace
- [x] 2.4 在 kernel API 中新增独立 `/planner/qa*` 聊天入口，使 Gateway 仅对 `Local` 模式优先调用 planner shell，同时保留 legacy `/qa`、`/qa/stream` 兼容回退

## 3. Gateway 编排切换

- [x] 3.1 更新 Gateway Python kernel 适配器与聊天服务，使 `Local` 聊天请求默认转发到 planner shell 入口
- [x] 3.2 为 Gateway 增加 planner shell 不可用时的兼容回退策略，保持前端入口与错误处理方式不变
- [x] 3.3 验证 Gateway 对前端输出的 `message`、`sources`、`messageEnd`、`error` 事件协议在新入口下保持兼容，并确认 `Web` / `Hybrid` 继续沿用旧链路

## 4. 测试与回归

- [x] 4.1 为 planner shell 增加单元测试，覆盖 state 传递、能力路由、legacy fallback 与异常降级
- [x] 4.2 为 kernel 聊天链路增加集成测试，覆盖 shell 入口下的 `Local` 场景、catalog/summary/fact QA/control 与 short-circuit 场景
- [x] 4.3 为 Gateway 增加集成测试，覆盖 `Local` 聊天请求走 planner shell、shell 不可用回退、`Web` / `Hybrid` 旧链路保持不变以及流式事件协议兼容
