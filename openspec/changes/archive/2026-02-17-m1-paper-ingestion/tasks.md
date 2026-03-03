## 1. 入口与项目结构

- [x] 1.1 新建 `app.ingest` CLI 入口，支持 `--input` 与 `--out` 参数解析，并在参数非法时返回非零退出码
- [x] 1.2 建立 ingest 模块骨架（`parser`/`chunker`/`writer`/`logging`）并定义统一数据模型（paper、chunk）
- [x] 1.3 按统一约定创建或补齐模块文件：`app/index_bm25.py`、`app/index_vec.py`、`app/graph_build.py`、`app/retrieve.py`、`app/expand.py`、`app/rerank.py`、`app/judge.py`、`app/generate.py`
- [x] 1.4 补齐项目目录骨架，确保 `data/`、`reports/`、`runs/` 存在并纳入开发流程

## 2. PDF 解析与元数据提取

- [x] 2.1 基于 PyMuPDF 实现 PDF 批量读取与逐页文本提取，仅纳入 `.pdf` 文件
- [x] 2.2 实现论文标题提取策略（metadata 优先，首页规则兜底）并生成稳定 `paper_id`
- [x] 2.3 实现页级异常捕获与日志记录，确保单页失败不终止整篇与整批

## 3. Chunk 化与页码追溯

- [x] 3.1 实现章节标题识别与分段逻辑，无法识别时回退到连续文本处理
- [x] 3.2 实现 300-500 token 近似窗口与约 50 token overlap 的滑窗切分
- [x] 3.3 为每个 chunk 生成 `chunk_id`、`paper_id`、`page_start`、`text`，并保证 `page_start` 可追溯

## 4. 输出落盘与可验证性

- [x] 4.1 实现 `data/processed/chunks.jsonl` 写入器（每行一个 chunk）
- [x] 4.2 实现 `data/processed/papers.json` 写入器（`paper_id/title/path` 映射）
- [x] 4.3 增加输出目录创建与覆盖策略，确保重复运行行为可预期
- [x] 4.4 实现单次运行目录写入：`runs/YYYYMMDD_HHMM/`，并保存结构化 JSON 轨迹
- [x] 4.5 在运行轨迹中记录输入问题、rewrite query、retrieval top-k+score、expansion 追加 chunk、rerank top-n+score、最终决策与回答
- [x] 4.6 对尚未启用阶段写入空数组或 null，保持日志 schema 稳定

## 5. 配置管理

- [x] 5.1 新建 `configs/default.yaml` 并定义 `chunk_size`、`overlap`、`top_k_retrieval`、`alpha_expansion`、`top_n_evidence`、`fusion_weight`、`RRF_k`、`sufficiency_threshold`
- [x] 5.2 实现配置加载逻辑，运行时优先读取 `configs/default.yaml` 并提供默认回退
- [x] 5.3 将 ingest 中的 chunk 参数改为从配置读取，移除同类硬编码常量

## 6. 验收与回归检查

- [x] 6.1 在至少 20 篇论文样本上运行 CLI，确认流程无崩溃并产出目标文件
- [x] 6.2 编写/补充字段完整性校验（chunk 必含 `chunk_id/paper_id/page_start/text`）
- [x] 6.3 对任取 3 篇论文随机抽样 5 个 chunk 做人工检查并记录结果（可读性与页码一致性）
- [x] 6.4 校验运行轨迹 JSON 字段完整性与分数字段可解析性
