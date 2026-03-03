## 为什么

当前检索流程缺少可复用的结构化图信号，导致后续扩展（相邻段扩展、实体链路扩展）只能依赖文本相似度，召回稳定性和可解释性不足。M4 需要先把 chunk 之间的结构关系沉淀为可查询图，作为后续检索增强的基础能力。

## 变更内容

- 新增基于 `chunks_clean.jsonl` 的图构建流程，输出 `data/processed/graph.json`（或兼容 `graph.pkl`）。
- 新增图查询 API：`neighbors(chunk_id, type=adjacent|entity, hop=1)`，并可选支持带权重结果。
- 新增建图过滤与边生成规则：
  - 仅对 `suppressed=false` 且 `content_type!="watermark"` 的 chunk 建图。
  - 默认跳过 `front_matter`。
  - 邻接边按同论文顺序建立；若存在 `section`，优先 section 内邻接。
  - 实体共现边按同论文内共享实体建立，并限制每点 top_m 邻居避免图爆炸。
- 新增实体抽取兜底：当输入缺少 `entities` 时，基于 `clean_text` 用规则抽取缩写、连字符数字词、CamelCase。

## 功能 (Capabilities)

### 新增功能
- `chunk-graph-construction`: 从清洗后的 chunk 构建邻接图和实体共现图，并提供基础查询接口与可加载图文件输出。

### 修改功能
（无）

## 影响

- 代码：`app/graph_build.py`（新增或扩展）、可能新增图加载/查询工具模块。
- 数据：新增 `data/processed/graph.json`（或 `graph.pkl`）产物。
- 配置：可能新增图构建参数（如 `entity_overlap_threshold`、`entity_top_m`、`include_front_matter`）。
- 测试与报告：新增图构建/查询单元测试与 M4 验收记录。
