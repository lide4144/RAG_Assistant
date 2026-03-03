## 1. Context Assembler 基础能力

- [x] 1.1 新增 `M7.7` 上下文组装入口，接收 `system_prompt`、`user_prompt`、`chat_history`、`evidence_grouped` 与 `max_context_tokens`
- [x] 1.2 实现统一 token 估算函数并输出 `prompt_tokens_est`
- [x] 1.3 生成 `assembled_prompt` 标准结构，保证当前轮用户问题始终保留

## 2. 预算裁剪策略实现

- [x] 2.1 实现历史优先裁剪：超预算时按时间从老到新删除 `chat_history`
- [x] 2.2 实现证据裁剪触发条件：仅当历史裁至 1 轮后才开始裁剪 `evidence_grouped`
- [x] 2.3 实现证据裁剪排序：优先丢弃 `payload.source=graph_expand` 且低 `score_rerank` chunk
- [x] 2.4 维护 `discarded_evidence` 输出，记录每个被裁剪 chunk 的关键标识与来源

## 3. 兜底与链路接入

- [x] 3.1 实现底线防御：证据数 `< 1` 时短路，不调用 LLM
- [x] 3.2 在短路路径追加 `output_warnings += context_overflow_fallback` 并返回“检索内容过长，无法生成答案”
- [x] 3.3 将 M7.7 接入 M7.5-B 调用前链路，替换旧的 prompt 拼装入口

## 4. 可观测性与测试验收

- [x] 4.1 增加运行日志字段：`prompt_tokens_est`、`discarded_evidence_count`、`history_trimmed_turns`、`context_overflow_fallback`
- [x] 4.2 编写单元测试覆盖三段裁剪优先级（历史优先、证据次之、证据为空短路）
- [x] 4.3 构造极端场景测试（`top_n_evidence=30` + 长图扩展文本）并断言 `discarded_evidence` 非空
- [x] 4.4 增加集成测试断言 LLM 调用路径不再抛出 `Token Limit Exceeded`
