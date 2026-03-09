## 为什么

当前 PDF 入库依赖简单文本抽取与首行回退策略，容易把 `Preprint. Under review.`、版权声明或会议页眉误识别为标题，导致元数据污染并直接影响检索与问答质量。现在引入 Marker 可以以较低集成成本显著提升论文结构解析质量，不应只修标题单点问题。

## 变更内容

- 在 PDF 入库链路中新增 Marker 解析路径，输出结构化 Markdown 与页面内容，用于元数据与 chunk 生成。
- 将标题抽取从“metadata/首行回退”升级为“结构化候选+质量门禁”机制，过滤占位文本、版权文本、模板文本。
- 扩展解析产物，支持更稳定的章节层级、公式与表格文本保真，以提升后续检索召回与证据可读性。
- 为 Marker 不可用或解析失败场景保留现有解析器回退路径，保证管线可用性。
- 在 ingest 报告与追踪中增加解析来源与质量信号，便于观测与回归。

## 功能 (Capabilities)

### 新增功能
- `marker-pdf-structured-parsing`: 使用 Marker 进行本地 PDF 结构化解析，并向入库阶段提供标题候选、章节结构与高保真正文文本。

### 修改功能
- `paper-ingestion-pipeline`: 调整 PDF 元数据抽取与 chunk 生成需求，支持多解析器路由、标题质量门禁、失败回退与解析可观测字段。

## 影响

- 受影响代码：`app/parser.py`、`app/ingest.py`、可能新增 `app/marker_parser.py` 及对应配置加载逻辑。
- 受影响产物：`papers.json`、`chunks.jsonl`、`paper_summary.json`、`runs/*/ingest_report.json` 字段语义与质量。
- 依赖变化：新增可选本地依赖（Marker 及其运行依赖），并需要同步更新 `requirements.txt`；同时定义可禁用开关与降级策略。
- 测试与运维：新增标题误判回归测试、解析器回退测试、端到端 ingest 质量基线。
