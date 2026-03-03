## 1. 策略与数据结构

- [x] 1.1 定义 M2.1 输出与运行日志数据结构，补齐 `scope_mode`、`query_used`、`papers_ranked`、`evidence_grouped` 字段契约
- [x] 1.2 在检索融合层实现 `front_matter/reference` 默认降权（建议 0.3）与作者机构/引用出处意图条件放行
- [x] 1.3 复核并保持 `watermark` 排除索引、`table_list` 降权策略与 M2.1 策略兼容

## 2. QA 流程改造

- [x] 2.1 在 QA 入口实现 Scope Policy 判定（`open|rewrite_scope|clarify_scope`）及指代词触发逻辑
- [x] 2.2 实现 `rewrite_scope` 路径的提示文案与 `query_used` 记录，保证可复现
- [x] 2.3 实现论文级聚合 `papers_ranked`（含 `score_paper` 与 `supporting_chunks`）
- [x] 2.4 实现 `evidence_grouped` 按论文分组输出（每篇 1~2 条，quote 来自 `text` 且 50~120 字）

## 3. 测试与评估记录

- [x] 3.1 增加检索与 QA 单元测试：覆盖 content_type 降权/条件放行与 scope policy 分流
- [x] 3.2 增加输出结构测试：校验 `papers_ranked` 与 `evidence_grouped` 字段完整性及分组约束
- [x] 3.3 增加运行日志校验：确保 M2.1 新字段被写入 runs 轨迹
- [x] 3.4 生成 `reports/m2_1_policy.md`，记录 5 个指代问题与 5 个作者机构问题的策略效果
