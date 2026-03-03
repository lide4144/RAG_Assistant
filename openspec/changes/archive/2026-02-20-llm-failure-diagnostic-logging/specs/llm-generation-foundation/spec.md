## MODIFIED Requirements

### 需求:LLM 调用失败不得中断主流程
任一 LLM 调用出现超时、限流、空响应、网络异常、HTTP 错误或解析失败时，系统必须将该次调用判定为失败并执行降级策略，禁止中断 QA 主链路。系统必须同时输出可追踪的结构化失败诊断信息，至少包括 `stage`、`reason`、`status_code`（若存在）、`attempts_used`、`max_retries`、`elapsed_ms` 与对应 fallback warning。

#### 场景:调用异常时流程连续
- **当** LLM 调用返回超时、429、空文本、网络异常、HTTP 错误或结构化解析失败
- **那么** 系统必须返回可用回答结果（规则改写或模板回答），并保留失败告警与结构化追踪信息

#### 场景:失败诊断字段齐全
- **当** rewrite 或 answer 的 LLM 调用失败
- **那么** 运行日志必须记录失败阶段、失败原因、重试与耗时信息，且与最终 fallback warning 保持一致
