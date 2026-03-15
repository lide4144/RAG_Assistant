## 1. 协议契约整理

- [x] 1.1 盘点当前 Gateway 已输出的 `message`、`sources`、`messageEnd`、`error` 事件结构与 Python kernel adapter 输入来源
- [x] 1.2 定义 agent 高层执行事件的有限类型集合与最小字段，覆盖 `planning`、`toolSelection`、`toolRunning`、`toolResult`、`fallback`
- [x] 1.3 明确 `fallback` 与 `error` 的语义边界、最小顺序约束和兼容缺省策略

## 2. Kernel 与 Gateway 适配

- [x] 2.1 在 Python kernel planner/runtime 到 Gateway 的协议层增加高层 agent 事件 envelope，禁止透传内部 trace 细节
- [x] 2.2 在 Gateway 事件适配层实现 agent 高层事件的校验、归一化和统一转发
- [x] 2.3 保证 Gateway 不引入 planner 决策、tool registry 解释或跨请求 agent 状态管理逻辑

## 3. 兼容与降级语义

- [x] 3.1 保持现有 `message`、`sources`、`messageEnd`、`error` 输出链路不变，使 agent 事件仅作为增强层并存
- [x] 3.2 在 planner fallback、tool fallback 和 legacy fallback 路径上补充统一 `fallback` 事件语义
- [x] 3.3 为未进入 agent-first 路径或后端未提供高层事件的请求保留旧协议兼容行为，禁止补造伪 agent 事件

## 4. 契约验证

- [x] 4.1 增加协议测试，覆盖 `planning -> toolSelection -> toolRunning -> toolResult` 的最小因果顺序
- [x] 4.2 增加协议测试，覆盖 `planning -> fallback -> message/messageEnd` 的受控降级路径
- [x] 4.3 增加协议测试，验证内部 trace 字段、私有节点名和未注册事件类型不会经由 Gateway 直接暴露给前端
