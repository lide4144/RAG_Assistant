## 上下文

当前 QA 主链路在 `rewrite` 与 `answer` 的 LLM 阶段均已支持失败降级，保证流程连续性。但观测面仅保留聚合 warning（例如 `llm_answer_timeout_fallback_to_template`），缺少排障所需的结构化上下文（失败阶段、错误类别、状态码、重试与耗时）。

这导致两类问题：
1. 线上回放时只能看到“降级发生”，无法判断“为什么降级”。
2. 评估报告可统计 fallback 次数，但无法定位具体失效模式并指导配置调优（timeout/retry/model/provider）。

## 目标 / 非目标

**目标：**
- 为 `rewrite` 与 `answer` 两个阶段定义统一的 LLM 失败诊断模型。
- 将诊断信息落盘到 `run_trace.json` 和 `qa_report.json`，支持按 run 追踪与横向统计。
- 保持现有 fallback 行为与用户可见回答路径不变。
- 诊断信息不包含密钥、完整提示词或敏感原文片段。

**非目标：**
- 不更换 LLM 提供方与模型。
- 不改造检索、rerank、证据分配与回答模板策略。
- 不引入外部可观测平台依赖（仅本地运行产物增强）。

## 决策

### 决策 1：采用“阶段化 + 结构化”诊断对象
- 方案：在 rewrite 与 answer 各自输出独立诊断对象，包含：`stage`、`provider`、`model`、`reason`、`status_code`、`attempts_used`、`max_retries`、`elapsed_ms`、`fallback_warning`、`timestamp`。
- 原因：可直接回答“哪里失败、失败类型、花了多久、重试是否耗尽”。
- 备选：
  - 仅记录 warning 字符串：实现简单，但信息密度不足。
  - 记录原始异常全文：信息全但噪声大，且可能暴露敏感上下文。

### 决策 2：保留 warning 作为摘要信号，诊断对象作为根因上下文
- 方案：`output_warnings` 继续保留；新增诊断对象与 warning 一一对应。
- 原因：兼容现有消费方，同时提供可定位信息。
- 备选：仅保留结构化对象并移除 warning，会破坏既有下游解析。

### 决策 3：失败字段向后兼容（可空）
- 方案：新增字段均允许 `null` 或对象缺省，成功调用时可为空。
- 原因：避免历史 run 与新 schema 冲突。
- 备选：强制非空会导致老数据与部分路径无法通过校验。

### 决策 4：限制诊断载荷，禁止敏感数据泄露
- 方案：不落盘 API key、完整 prompt、完整 response body；仅在需要时记录短摘要（长度受限）。
- 原因：平衡排障价值与数据安全。
- 备选：落盘完整请求响应虽易排错，但安全风险不可接受。

## 风险 / 权衡

- [风险] 字段过多影响 trace 可读性 → [缓解] 使用固定扁平字段并限制可选扩展字段数量。
- [风险] 下游脚本依赖旧 schema → [缓解] 新字段采用可选策略，旧字段不变。
- [风险] 部分异常无法稳定映射 reason → [缓解] 统一归并到 `unknown_error`，并保留状态码/阶段/耗时。
- [风险] 诊断对象与 warning 不一致 → [缓解] 增加一致性规则：存在 fallback warning 时必须有对应诊断对象。

## Migration Plan

1. 先扩展 LLM 调用结果结构与 reason 归一规则。
2. 在 rewrite/answer 调用处注入阶段化诊断对象并写入 trace/report。
3. 扩展 `runlog` 校验，允许新字段并校验核心类型。
4. 回归验证：
   - 成功路径（无 fallback）
   - timeout/rate_limit/http_error/invalid_json 路径
   - 缺失 API key 路径
5. 若发现兼容问题，可回滚为“仅 warning 模式”，不影响主流程回答。

## Open Questions

- 是否需要为 `qa_report.json` 增加诊断字段采样开关（例如仅失败时写入）？
- `http_error` 是否需要细分 `4xx` 与 `5xx` 子类以支持自动化告警阈值？
- 是否应在后续变更中为诊断字段提供聚合报告脚本（按 reason 聚类）？
