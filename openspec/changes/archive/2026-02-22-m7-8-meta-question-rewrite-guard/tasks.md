## 1. Rewrite 护栏实现

- [x] 1.1 在 rewrite 流程中新增 `meta_guard` 阶段，放置于 `standalone_query` 生成后、最终 `rewrite_query` 决策前
- [x] 1.2 实现元问题模式识别（中英触发词与规则匹配），输出 `rewrite_meta_detected`
- [x] 1.3 实现元问题意图转写逻辑：基于 `entities_from_history` 生成事实检索 query，禁止状态词直传检索
- [x] 1.4 实现机械拼接防护校验，拒绝“历史问句 + 当前问句”直接拼接结果

## 2. 状态联动与降级路径

- [x] 2.1 接入 `last_turn_decision` 与 `last_turn_warnings` 到 rewrite 输入契约
- [x] 2.2 落实执行顺序：先 clarify 合并（M7.6），再元问题护栏判断
- [x] 2.3 在命中 `insufficient_evidence_for_answer` 时优先转写为补证据检索目标
- [x] 2.4 实现 LLM rewrite 异常回退（空串/污染串/越界任务）到规则改写并记录回退原因

## 3. 可观测性与契约对齐

- [x] 3.1 在 rewrite 输出与 trace 中新增 `rewrite_guard_applied`、`rewrite_guard_strategy`、`rewrite_notes`
- [x] 3.2 确保新增字段序列化兼容，不改变既有输出结构与 Gate 位置
- [x] 3.3 更新相关 schema/类型定义与日志映射，补齐字段默认值策略

## 4. 测试与评估交付

- [x] 4.1 构造至少 10 个元问题追问样本（含中英混合）并形成可复现测试集
- [x] 4.2 为关键案例增加回归用例：`Transformer 有什么用处、由什么组成？` -> `Why does it lack of evidences?`
- [x] 4.3 验证 100% 样本无机械拼接 query，且 `rewrite_meta_detected/rewrite_guard_applied` 可追踪
- [x] 4.4 评估证据质量变化并统计 Gate 触发变化，输出 `reports/m7_8_meta_question_guard.md`
