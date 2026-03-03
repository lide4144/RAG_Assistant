## 为什么

当前系统在 `llm rewrite` 与 `llm answer` 失败时会回退到规则/模板路径，但运行产物通常只保留简化 warning（例如 timeout fallback）。这会导致排障时无法快速判断是超时、网络、HTTP 状态、重试耗尽还是响应解析问题。

## 变更内容

- 为 `llm rewrite` 与 `llm answer` 增加结构化失败诊断字段，覆盖失败类型、HTTP 状态码、重试次数、耗时与阶段信息。
- 将诊断信息写入 `run_trace.json` 与 `qa_report.json`，在不暴露敏感信息的前提下支持稳定复现与审计。
- 统一 fallback warning 与诊断字段的对应关系，确保 warning 可读、诊断可定位。
- 保持主流程“失败可降级不中断”的既有行为不变。

## 功能 (Capabilities)

### 新增功能
- `llm-failure-diagnostics-observability`: 为 LLM rewrite/answer 失败建立统一、可落盘、可追踪的诊断观测模型。

### 修改功能
- `llm-generation-foundation`: 补充 LLM 调用失败时的诊断日志最小字段要求与约束。
- `output-consistency-evidence-allocation`: 扩展 QA 输出结构，纳入 answer/rewrite 的失败诊断字段与一致性规则。

## 影响

- 受影响代码：`app/llm_client.py`、`app/rewrite.py`、`app/qa.py`、`app/runlog.py`。
- 受影响产物：`runs/*/run_trace.json`、`runs/*/qa_report.json`、相关验收报告。
- 外部 API 与索引格式无破坏性变化；新增字段默认向后兼容（可选/可空）。
