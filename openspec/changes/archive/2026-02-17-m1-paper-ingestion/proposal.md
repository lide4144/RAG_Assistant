## 为什么

当前项目缺少可复用的论文入库流水线，导致后续检索与问答能力无法建立稳定数据基础。现在优先完成 M1，可以尽快把本地 PDF 批量转换为可检索 chunk 数据，为后续检索、排序与生成阶段提供统一输入。

## 变更内容

- 新增一条最小可用的论文入库 CLI：`python -m app.ingest --input data/papers --out data/processed`。
- 新增 PDF 解析与 chunk 化流程：读取 `data/papers/*.pdf`，提取正文，按标题边界与滑窗策略生成 chunk。
- 新增结构化输出：
  - `data/processed/chunks.jsonl`：每行一个 chunk，至少包含 `chunk_id`、`paper_id`、`page_start`、`text`。
  - `data/processed/papers.json`：保存 `paper_id` 与标题、源路径映射。
- 新增稳健性机制：遇到异常页可跳过并记录日志，避免单篇异常中断整批处理。
- 新增统一开发约定：
  - 运行过程日志统一输出到 `runs/YYYYMMDD_HHMM/*.json`，记录问题、检索、扩展、重排与最终决策等关键轨迹。
  - 所有关键超参数统一配置到 `configs/default.yaml`。
  - 代码目录按约定模块组织（`app/ingest.py`、`app/retrieve.py`、`app/rerank.py` 等）。
- 本阶段不引入外部解析服务（如 GROBID），仅在风险备注中预留后续增强路径。

## 功能 (Capabilities)

### 新增功能
- `paper-ingestion-pipeline`: 批量解析本地 PDF、执行 chunk 化并输出可检索数据文件。
- `pipeline-development-conventions`: 统一运行日志、超参数配置与模块目录约定。

### 修改功能

## 影响

- 代码影响：新增/扩展 `app.ingest` CLI、PDF 解析模块、chunk 构建模块、落盘与日志模块。
- 依赖影响：引入或确认 `PyMuPDF (fitz)` 作为 PDF 文本解析依赖。
- 数据影响：新增 `data/processed/chunks.jsonl` 与 `data/processed/papers.json` 的产物格式约束。
- 工程影响：新增 `configs/default.yaml` 与 `runs/` 运行轨迹落盘约束，并统一 `app/` 模块命名结构。
- 验收影响：需要在至少 20 篇论文上进行批处理验证与抽样人工检查（可读性与页码正确性）。
