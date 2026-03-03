## 为什么

当前 `chunks.jsonl` 的原始文本包含水印、URL、控制符和疑似乱码，且同页短碎片会破坏检索稳定性，导致召回与排序噪声偏高。需要在进入 BM25/向量检索前增加统一清洗与质量标注层，以提升可检索性和证据可用性。

## 变更内容

- 新增 M1.5 清洗产物：基于 `data/processed/chunks.jsonl` 生成 `data/processed/chunks_clean.jsonl`。
- 为每个 chunk 增加字段：`clean_text`、`content_type`、`quality_flags`、`section`（可空）。
- 实现强制规则：
  - 水印行过滤（指定关键词，不区分大小写）。
  - URL 归一化为 `<URL>`，并标注 `has_url`。
  - 控制符清除与连续空白折叠。
  - `weird_char_ratio > 0.35` 时追加 `garbled` 标记（不删原文）。
  - 基于规则的 `content_type` 分类：`appendix`、`dialogue_script`、`reference`、`front_matter`、`watermark`、`formula_block`、`body`。
- 实现“同页短碎片合并”规则：
  - 在同一 `paper_id + page_start` 内按 `chunk_id` 扫描，连续满足 `len(text)<=40` 且数量 `>=6` 时合并为 `table_list` block。
  - block 的 `clean_text` 以换行拼接，追加 `short_fragment_merged`，并保留 `merged_from`（可选）。
- 检索侧策略调整：`content_type=table_list` 的条目在融合分数降权（如 `*0.5`），但保留证据可引用能力。
- 验收样例必须通过（5 条指定 chunk 断言）。

## 功能 (Capabilities)

### 新增功能

### 修改功能
- `paper-ingestion-pipeline`: 扩展入库后处理规范，增加 chunk 清洗、质量标注、内容类型识别与短碎片合并输出要求。
- `pipeline-development-conventions`: 增加面向检索阶段的清洗产物约定与 `table_list` 降权但可引用的检索策略约定。

## 影响

- 代码影响：新增/修改清洗与标注模块、ingest 后处理流程、检索融合打分逻辑。
- 数据影响：新增 `data/processed/chunks_clean.jsonl`；原 `chunks.jsonl` 保持兼容。
- 验证影响：新增针对水印过滤、URL 归一化、content_type 分类、短碎片合并、样例断言的测试。
