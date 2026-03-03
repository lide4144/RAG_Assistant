## 1. 索引与数据准备

- [x] 1.1 实现从 `data/processed/chunks_clean.jsonl` 加载 chunk 的公共读取逻辑，并过滤 `content_type=watermark`
- [x] 1.2 完成 `app/index_bm25.py` 的 BM25 索引构建与加载接口（索引字段使用 `clean_text`）
- [x] 1.3 完成 `app/index_vec.py` 的向量索引构建与加载接口（索引字段使用 `clean_text`）
- [x] 1.4 增加索引构建命令或入口，确保可单独构建 BM25 与向量索引产物

## 2. 检索与 QA CLI

- [x] 2.1 在 `app/retrieve.py` 实现 `dense|bm25|hybrid` 三种检索模式并返回统一候选结构
- [x] 2.2 在 hybrid 融合流程中加入 `table_list` 降权（读取 `table_list_downweight`），且不剔除该候选
- [x] 2.3 在候选输出中保留 `text` 字段以支持 quote 生成，并确保 quote 截取来自原始 `text`
- [x] 2.4 新增 `app/qa.py` CLI：`python -m app.qa --q "..." --mode dense|bm25|hybrid`
- [x] 2.5 实现 QA 输出格式：Answer + Top-5 evidence（`chunk_id + section/page + quote`）

## 3. 日志、评估与验收

- [x] 3.1 为 QA 运行新增轨迹落盘，记录 query、mode、retrieval top-k、最终 evidence 与最终回答
- [x] 3.2 补充测试：dense/bm25/hybrid 均返回可用 top-k；watermark 过滤生效；table_list 降权生效且可保留
- [x] 3.3 补充测试：evidence quote 来自原始 `text` 而非 `clean_text`
- [x] 3.4 生成 `reports/m2_baseline.md`，记录至少 10 个问题及其输出 evidence
- [x] 3.5 执行 M2 验收检查，完成 30 个自制问题主观相关性验证并记录结果
