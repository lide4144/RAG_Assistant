## 1. 扩展召回核心实现

- [x] 1.1 在 `app/retrieve.py` 或 `app/expand.py` 实现图扩展入口：输入 seed candidates、query、graph API、alpha/max 上限，输出扩展后候选与统计
- [x] 1.2 实现 1-hop 双类型扩展（`adjacent` + `entity`），确保对每个 seed 都尝试两类邻居
- [x] 1.3 实现扩展候选去重（按 `chunk_id`）与来源标记（seed/adjacent/entity）

## 2. 过滤与预算控制

- [x] 2.1 实现扩展候选强过滤：`watermark` 直接剔除，`front_matter/reference` 按 query 意图词门控
- [x] 2.2 实现扩展规模约束：`<= top_k * (1 + alpha)` 且全局上限 `<= 200`
- [x] 2.3 在预算耗尽、无邻居、重复命中等路径下补齐稳定回退逻辑

## 3. QA 链路接入与可观测性

- [x] 3.1 在 `app/qa.py` 检索阶段接入“初检 + 图扩展”候选合并流程
- [x] 3.2 在 run trace/qa report 增加扩展统计字段（扩展新增数、过滤数、来源分布、最终候选数）
- [x] 3.3 更新 `configs/default.yaml` 增加 `graph_expand_alpha`、`graph_expand_max_candidates` 与扩展意图词配置

## 4. 测试与验收

- [x] 4.1 新增单元测试：双类型扩展触发、过滤规则、去重规则、预算上限
- [x] 4.2 新增集成测试：QA 主流程在开启扩展时可稳定返回并保留 seed 候选
- [x] 4.3 产出 M5 验收记录：至少 10 个多跳/对比问题，记录扩展前后关键上下文补全情况
