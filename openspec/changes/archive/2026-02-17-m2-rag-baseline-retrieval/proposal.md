## 为什么

当前系统已完成论文入库与清洗标注，但还缺少最小可用问答链路，无法对问题执行检索、融合和证据化回答。现在进入 M2，需要落地可运行的 BM25/向量/混合检索与基础 QA CLI，验证从问题到证据输出的闭环。

## 变更内容

- 新增基础检索与问答能力：基于 `chunks_clean.jsonl` 建立 BM25 与向量索引，支持 `dense|bm25|hybrid` 三种模式。
- 新增最小 QA CLI：`python -m app.qa --q "..." --mode dense|bm25|hybrid`，输出简短答案和 Top-5 evidence（chunk_id + section/page + quote）。
- 增加融合策略约束：`content_type=table_list` 候选降权（默认 *0.5），`content_type=watermark` 不进入索引。
- 固化证据引用规则：检索文本字段使用 `clean_text`，引用片段必须来自原始 `text`。
- 增加 M2 基线评估记录：产出 `reports/m2_baseline.md`，记录 10 个问题的回答与证据。

## 功能 (Capabilities)

### 新增功能
- `rag-baseline-retrieval`: 定义 BM25/向量/混合检索、QA CLI、证据输出格式与 M2 验收标准。

### 修改功能
- `pipeline-development-conventions`: 补充 M2 阶段评估记录与运行可复现日志在检索链路中的落盘约束。

## 影响

- 代码影响：`app/index_bm25.py`、`app/index_vec.py`、`app/retrieve.py`、`app/generate.py`、`app/qa.py` 及相关数据读取模块。
- 数据影响：使用 `data/processed/chunks_clean.jsonl` 建索引，新增索引产物目录与 QA 运行输出。
- 配置影响：沿用 `configs/default.yaml` 的检索与融合参数（如 `top_k_retrieval`、`fusion_weight`、`table_list_downweight`）。
- 文档与评估：新增 `reports/m2_baseline.md`，并更新运行说明。
