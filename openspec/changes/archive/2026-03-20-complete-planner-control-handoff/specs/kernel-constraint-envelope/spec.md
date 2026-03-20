## ADDED Requirements

### 需求:系统必须为底层执行链提供统一约束信封
系统必须要求 `kernel / qa（内核 / 问答链）`、`tool execution（工具执行）` 与 `guardrails（护栏）` 在需要上报阻塞或降级信息时返回统一的 `constraints envelope（约束信封）`。该结构至少必须包含 `constraint_type（约束类型）`、`reason_code（原因代码）`、`severity（严重度）`、`retryable（是否可重试）`、`blocking_scope（阻塞范围）` 与 `user_safe_summary（面向用户的安全摘要）`。禁止继续使用散落布尔字段、未结构化错误文本或私有临时标志作为唯一约束表达。

#### 场景:底层统一返回约束信封
- **当** 底层执行链命中证据不足、引用不合法、依赖缺失或空结果
- **那么** 系统必须返回结构化的 `constraints envelope（约束信封）`，而不是仅返回自由文本错误

### 需求:约束信封必须包含可供 planner 决策的最小上下文
每个 `constraints envelope（约束信封）` 必须至少提供 `evidence_snapshot（证据快照）`、`citation_status（引用状态）`、`failed_dependency（失败依赖）` 或 `suggested_next_actions（建议后续动作）` 中的必要字段，以支持 `planner / policy（规划器 / 策略层）` 判断是进入 `clarify（澄清）`、`partial_answer（部分回答）`、`refuse（拒答）` 还是 `delegate（委托）`。禁止让 planner 在缺少必要上下文的情况下猜测底层约束语义。

#### 场景:planner 可以基于约束信封做决策
- **当** 一次请求的底层执行链返回约束信封
- **那么** `planner / policy（规划器 / 策略层）` 必须能够仅依据其结构化字段判断下一步交互姿态，而不需要反向解析底层私有日志

### 需求:约束信封必须可在 trace 中稳定还原
系统必须在运行 trace（运行追踪）中记录每轮请求收到的关键 `constraints envelope（约束信封）` 摘要，包括 `constraint_type（约束类型）`、`reason_code（原因代码）`、`severity（严重度）` 与是否阻断最终答案成型。禁止让底层约束仅存在于瞬时内存或零散 debug 输出中。

#### 场景:约束信封可审计
- **当** 请求因底层约束而未直接进入正常执行
- **那么** trace 中必须能够还原约束信封摘要，并区分这是 `guardrail block（护栏阻断）` 还是普通执行告警
