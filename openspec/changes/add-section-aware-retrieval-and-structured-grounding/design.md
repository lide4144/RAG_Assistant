## 上下文

当前系统的主路径是“query rewrite -> chunk retrieval -> graph expansion -> rerank -> evidence_grouped -> answer -> evidence gate”。这条链路对局部事实问答有效，但对论文结构类问题存在两个缺口：

1. 检索层只有摘要层粗召回和 chunk 级精检索，没有 section/tree 索引，导致“目录、章节、某节内容”这类问题只能靠正文 chunk 碰运气。
2. 门控层以自然语言回答为输入提取关键结论，再做 citation 与 quote 的后验匹配；这种方法对数字、实验结论有效，但对列表编号、页码、标题编号等格式性文本容易误报。

现有仓库已经具备两类可复用资产：
- `marker-pdf-structured-parsing` 已要求保留结构化正文与章节层级信息，但尚未形成稳定的 section 检索对象。
- `graph-expansion-retrieval` 已能补全 chunk 候选，但其优势在多跳/关系补全，不适合作为章节结构问答的主检索器。

新增设计必须满足两个约束：
- 不能把系统彻底重写成另一套 GraphRAG；要复用现有 ingest、retrieval、qa report、trace 结构。
- 必须考虑 Marker 对复杂 PDF 的脆弱性，避免结构索引成为新的单点失败。

## 目标 / 非目标

**目标：**
- 为论文结构类问题提供专用的 section-aware retrieval 路由，而不是继续依赖普通 chunk 检索。
- 在 ingest 阶段产出可检索的章节树与 section 元数据，并与 chunk 建立父子映射。
- 将 Evidence Policy Gate 升级为“结构化 claim 绑定优先，文本后验校验兜底”的流程，减少格式性数字误杀。
- 对 Marker 标题层级提取失败提供显式、可审计的回退路径与运行观测。

**非目标：**
- 不在本变更中引入外部 GraphRAG 框架或新数据库产品。
- 不在本变更中实现论文级自动摘要树（如 RAPTOR 全量层次摘要）。
- 不要求现有所有问题都走 section retrieval；仅对识别出的结构类问题启用。
- 不移除现有 chunk evidence / graph expansion / rerank 链路，只调整优先级与接入顺序。

## 决策

### 决策 1：新增 `document-structure-retrieval` 能力，而不是把章节问题继续塞给 graph expansion

- 选择：在 ingest 时基于 Marker 中间表示构建 `section_id / section_title / section_level / heading_path / start_page / end_page / parent_section_id / child_chunk_ids`，并在 QA 中新增结构查询路由。
- 原因：论文结构问题本质上是文档层级检索，不是实体关系检索。章节标题与页码范围天然来自版面结构，直接建 section index 的召回稳定性更高。
- 备选方案：
  - 继续依赖现有 chunk + graph expansion：实现成本低，但对目录类问题仍是碰运气。
  - 直接引入树状摘要检索：长期有价值，但对当前仓库改动过大，且需要新的摘要构建与增量维护机制。

### 决策 2：结构检索依赖 Marker 输出，但必须有质量门禁与显式降级

- 选择：为 Marker 章节树增加质量状态，例如 `structure_parse_status=ready|degraded|unavailable`；当标题层级缺失、顺序混乱或无法形成稳定树时，不建立结构索引或标为不可用。
- 原因：`Marker` 对复杂 PDF 版式并非稳定可靠。若不显式暴露失败状态，系统会错误地把“不完整结构”当“完整目录”使用。
- 备选方案：
  - 无条件相信 Marker：最简单，但会让错误结构污染检索与回答。
  - 结构失败时直接拒绝问答：过于激进，会让系统可用性大幅下降。

### 决策 3：结构类问题采用“section retrieval -> chunk evidence supplement -> answer”

- 选择：在 query routing 中识别“章节/目录/第几节/结构”意图。命中后优先检索 section index，返回相关 section；再按 `child_chunk_ids` 或邻接 chunk 补全 chunk 证据，最终回答仍以 chunk 证据为引用落点。
- 原因：这样既能利用 section 层的结构召回，又不破坏“最终事实引用必须落到 chunk”这一现有契约。
- 备选方案：
  - 直接用 section summary 作为最终 citation：会破坏已有 `answer_citations` 约束，也弱化证据可追溯性。
  - 只返回 section title 不补 chunk：对用户可读，但无法满足后续 gate 和引用绑定。

### 决策 4：Evidence Policy Gate 采用结构化 claim 绑定优先，文本校验退为兜底

- 选择：回答阶段先产出结构化 `claims[]`，每条 claim 必须显式绑定 `chunk_id`，可选补充 `section_id`。自然语言答案由已绑定 claim 渲染；门控优先校验 claim 绑定是否完整，再对必要场景执行文本一致性兜底。
- 原因：关键结论应当先结构化再渲染，不能继续完全从自然语言里反推 claim，否则列表编号、页码等格式性文本始终会产生误判空间。
- 备选方案：
  - 继续扩充正则黑名单：只能止血，无法从机制上消除误判。
  - 使用独立 judge LLM 作为主门控：语义能力更强，但成本更高、可重复性更弱，不适合作为当前主判据。

### 决策 5：graph expansion 保留，但下沉为 section/chunk 检索的补充扩展器

- 选择：当 structure route 已命中 section 后，graph expansion 仅在需要补全方法、实体关系或邻接实验信息时参与候选扩展；默认不用于生成论文目录或章节树。
- 原因：graph 擅长关系补全，不擅长恢复文档层级。保留资产复用，但避免职责错位。
- 备选方案：
  - 完全禁用 graph：会丢失已有多跳补全优势。
  - 让 graph 同时承担结构召回：信号噪声高，调试复杂度更大。

## 风险 / 权衡

- [风险] `Marker` 在双栏、旧论文或非标准标题样式 PDF 上无法稳定抽出章节树。  
  缓解措施：加入结构质量门禁与 `structure_parse_status`；当状态非 `ready` 时，结构类问题降级回 chunk 检索，并在回答/trace 中明确提示“文档结构不可稳定解析”。

- [风险] 新增 section index 会增加 ingest 产物与索引维护复杂度。  
  缓解措施：首版优先使用轻量文件/JSON 索引并与现有 `paper_id`/`chunk_id` 对齐，不引入新存储后端。

- [风险] 结构查询路由误判，可能把普通事实问题送入 section retrieval。  
  缓解措施：仅对强结构词模式启用；命中后仍允许 section retrieval 为空时回退原路径，并记录 `structure_route_fallback`。

- [风险] 结构化 claim 绑定会增加回答阶段复杂度，短期可能拉长输出路径。  
  缓解措施：首版仅要求结构类回答和高风险答案走 claim 绑定；保留兼容路径与 trace 字段，逐步扩大覆盖面。

- [风险] section retrieval 与 chunk retrieval 同时存在，可能引发上下游指标口径混乱。  
  缓解措施：在 `run_trace` / `qa_report` 中新增显式字段区分 `retrieval_route`、`section_candidates_count`、`structure_parse_status`、`claim_binding_mode`。

## Migration Plan

1. 先在 ingest 阶段增加 section 元数据产物与 Marker 结构质量状态，不改变现有 QA 默认路径。
2. 再在 QA 路由中接入结构类问题识别，并为 structure route 增加回退字段与观测。
3. 随后在回答阶段引入结构化 claim 绑定，但先保持现有 textual gate 作为兼容兜底。
4. 完成回归与评测后，再收紧 Evidence Policy Gate：结构化 claim 绑定成为主路径，文本规则仅保留少量兼容保护。
5. 若上线后发现 Marker 结构失败率过高，可通过配置关闭 structure route，系统回退到既有 chunk 检索，不影响主链路可用性。

## Open Questions

- section 索引首版是否仅覆盖显式标题节点，还是需要同时把图表标题也纳入结构对象？
- claim 绑定输出是直接扩展现有 `answer_citations`，还是新增 `answer_claims` 字段后由 UI/trace 同时展示？
- 对“章节结构不可解析”的用户提示，是只写入 trace，还是也要在最终回答中显式披露？
