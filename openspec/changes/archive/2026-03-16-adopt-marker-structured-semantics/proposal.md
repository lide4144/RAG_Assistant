## 为什么

当前 PDF 导入已经接入 Marker，但成功解析后的结构信息仍存在“部分生成、部分丢失、部分未优先消费”的情况。最明显的是标题决策仍主要表现为“候选混选 + 通用打分”，没有把 Marker 的结构语义当作第一证据源；同时表格/公式等 block 语义和 markdown 结构在成功路径里没有被稳定保留下游，更没有贯通进入 chunking、retrieval weighting 与 citation，导致系统虽然“用了 Marker”，却没有完整兑现“结构化信任”。

## 变更内容

- 将 PDF 标题决策从“来源无感知的候选竞争”调整为“结构化信任”策略。
- 当 `parser_engine=marker` 且未回退时，优先依据 Marker 的标题层级语义选择候选，按 `H1/顶层标题 -> H2/次级标题 -> markdown 首行 -> metadata/首页首行` 的顺序降级。
- 保留现有黑名单与置信度门禁，但要求其建立在结构化来源优先级之上，而不是让所有来源同权竞争。
- 要求 Marker 成功解析后保留足够的结构语义进入中间表示，至少不能在成功路径中静默丢失 block 类型与 markdown 结构来源。
- 将 Marker 的表格/公式类型语义一路接入 chunking、retrieval weighting 与 citation 生成，使这些结构块不再只停留在调试或中间态。
- 明确区分“结构类查询优先使用章节树”与“普通查询仍走 chunk 路由”的边界，同时补充结构化信息是否被实际消费的诊断字段。
- 为标题决策补充更细的可观测字段，便于区分“Marker 未识别标题”和“Marker 识别了但决策未采用”。
- 收紧历史标题修复路径的要求，使其能够基于结构化来源重建，而不是仅复用现有落盘标题。

## 功能 (Capabilities)

### 新增功能
<!-- 无 -->

### 修改功能
- `marker-pdf-structured-parsing`: 调整标题候选选择语义，并要求成功解析后的 block 类型、markdown 来源与结构诊断信息可稳定进入中间表示，而不是在归一化过程中被静默降级。
- `paper-ingestion-pipeline`: 调整 PDF 标题落库、结构化信息落盘、chunking 输入与历史修复的要求，要求标题决策、落盘与诊断都能反映结构化信任路径。
- `unified-source-citation-contract`: 调整 citation 生成要求，使表格/公式等结构化块在被采用为证据时能携带可消费的结构 provenance，而不是被伪装成普通正文片段。

## 影响

- 受影响代码：`app/marker_parser.py`、`app/parser.py`、`app/ingest.py`、`app/chunker.py`、`app/retrieve.py`、`app/qa.py`、历史修复脚本与相关测试。
- 受影响产物：`papers.json`、`chunks.jsonl`、`runs/*/ingest_report.json`、结构化中间表示、citation 结构、可能的 marker artifact 调试输出与标题修复脚本行为。
- 受影响规范：`marker-pdf-structured-parsing`、`paper-ingestion-pipeline`、`unified-source-citation-contract`。
- 测试与运维：需要补充“主标题 vs 章节标题竞争”“Marker 成功但标题误选”“block_type 在中间表示中不丢失”“表格/公式块进入 retrieval weighting 与 citation”“历史重建沿用结构化候选”的回归样例。
