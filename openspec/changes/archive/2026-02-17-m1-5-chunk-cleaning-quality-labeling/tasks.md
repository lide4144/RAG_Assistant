## 1. 清洗流程与数据模型

- [x] 1.1 新增清洗 CLI（建议 `python -m app.clean_chunks`），支持 `--input data/processed/chunks.jsonl --out data/processed/chunks_clean.jsonl`
- [x] 1.2 定义清洗后 chunk 记录结构，包含 `clean_text`、`content_type`、`quality_flags`、`section`（可空）及可选 `merged_from`
- [x] 1.3 确保输出保留原始 `text` 且不破坏现有 `chunks.jsonl` 产出

## 2. 规则实现

- [x] 2.1 实现水印行过滤（不区分大小写，命中指定关键词整行删除）
- [x] 2.2 实现 URL 归一化为 `<URL>`，并在 `quality_flags` 追加 `has_url`
- [x] 2.3 实现控制符清除与连续空白折叠
- [x] 2.4 实现 `weird_char_ratio` 检测，阈值 `>0.35` 时追加 `garbled`
- [x] 2.5 实现 `content_type` 规则分类：`appendix`、`dialogue_script`、`reference`、`front_matter`、`watermark`、`formula_block`、`body`

## 3. 同页短碎片合并

- [x] 3.1 按 `paper_id + page_start` 分组并按 `chunk_id` 顺序扫描连续条目
- [x] 3.2 实现连续 `len(text)<=40` 且数量 `>=6` 的合并逻辑，输出 `content_type=table_list`
- [x] 3.3 合并后 `clean_text` 用换行拼接，`quality_flags` 追加 `short_fragment_merged`，并记录 `merged_from`（可选）

## 4. 检索侧策略接入

- [x] 4.1 在融合打分中对 `content_type=table_list` 应用降权（默认 `*0.5`）
- [x] 4.2 保证 `table_list` 条目降权后仍可进入证据引用链路
- [x] 4.3 将降权系数配置化（例如 `table_list_downweight`），缺失时回退默认值

## 5. 验证与回归

- [x] 5.1 新增规则级单测：水印过滤、URL 归一化、控制符清理、乱码标记、content_type 分类
- [x] 5.2 新增短碎片合并单测：阈值边界、连续性、跨页不合并
- [x] 5.3 新增验收样例测试并通过：`eff6f9d4b754:00109`、`eff6f9d4b754:00094`、`eff6f9d4b754:00093`、`eff6f9d4b754:00095`、`67978670bdb6:00004`
- [x] 5.4 运行端到端检查，确认 `chunks_clean.jsonl` 结构与下游读取兼容
