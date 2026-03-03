## 为什么

在多轮追问中，用户常提出“为什么没有证据/为什么没答全”这类系统状态元问题。当前 rewrite 在该场景可能发生机械拼接或状态词污染，导致检索 query 偏离事实检索目标，进而降低证据命中质量并放大 `insufficient_evidence_for_answer` 连锁触发。

## 变更内容

- 为 rewrite 增加“元问题意图护栏（State-aware Rewrite Guard）”：识别状态追问并转写为面向事实补证的可检索查询。
- 强化 `standalone_query` 约束：实体完整、意图纯净、可检索，禁止“上一轮问题 + 当前问题”机械拼接。
- 与 M7.6 联动：当上一轮为 `clarify` 时先执行 clarify 合并，再做元问题护栏判断。
- 与 M8 联动：当上一轮包含 `insufficient_evidence_for_answer` 告警时，元问题优先转写为补证据检索目标。
- 新增 rewrite 可观测字段：`rewrite_meta_detected`、`rewrite_guard_applied`、`rewrite_guard_strategy`、`rewrite_notes`。
- 增加失败降级：LLM rewrite 异常时回退规则改写并记录回退原因。

## 功能 (Capabilities)

### 新增功能
- 无

### 修改功能
- `query-rewriting`: 增加元问题识别、意图转写、机械拼接禁止、LLM 失败降级与新追踪字段要求。
- `multi-turn-session-state`: 明确 rewrite 读取历史实体与上一轮决策/告警信号，保证与 clarify 状态机联动顺序。

## 影响

- 受影响模块：rewrite pipeline（rule/llm 路径）、多轮状态读取与字段映射、运行日志/trace。
- 不变更模块：retrieval、graph、rerank、gate 的架构位置与输出结构。
- 交付物：增量 specs、可执行任务清单、评估报告 `reports/m7_8_meta_question_guard.md`。
