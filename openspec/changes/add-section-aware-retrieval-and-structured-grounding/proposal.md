## 为什么

当前论文问答链路对“这篇论文有多少章节”“第 3.1 节讲了什么”“整篇结构如何”这类全局结构问题缺少专用检索路径，导致系统只能在 chunk 级正文中碰运气召回局部证据。与此同时，现有 Evidence Policy Gate 仍以回答文本后处理为主，容易把列表编号、标题编号等排版信息误判为数值型关键结论，造成假阳性拒答。

仓库已经具备 Marker 结构化解析与 graph expansion 雏形，但尚未把 PDF 的标题层级、章节树和 chunk 证据绑定成一条面向论文结构问答的稳定链路。现在需要把这些已有资产扩展为 section-aware retrieval 与 structured grounding，减少“检索不到目录”和“门控误杀”两类系统性问题。

## 变更内容

- 新增文档结构检索能力：基于 Marker 结构化解析产出章节树与 section 元数据，支持按章节标题、层级路径和页码范围建立结构索引。
- 在 QA 路由中新增“结构类问题”识别，对“章节/目录/第几节/结构概览”类问题优先走 section retrieval，再补充 chunk 级证据。
- 新增 Marker 结构解析兜底策略：当标题层级抽取失败或质量不足时，系统必须显式降级到既有 chunk 检索，并记录“结构不可解析”状态，而不是静默假装存在章节索引。
- 将 Evidence Policy Gate 从“自然语言后验硬匹配”升级为“结构化 claim -> source 绑定优先”的门控流程，避免把排版编号误判为关键数字结论。
- 保持 graph expansion 作为结构检索后的补充证据扩展器，而不是继续承担论文目录/章节结构问题的主召回职责。

## 功能 (Capabilities)

### 新增功能
- `document-structure-retrieval`: 定义章节树索引、结构类问题路由、section retrieval 与回退行为，支撑论文结构问答。

### 修改功能
- `marker-pdf-structured-parsing`: 新增章节树/标题层级中间表示与结构解析失败兜底要求。
- `rag-baseline-retrieval`: 在既有摘要层/chunk 层检索之外，引入面向结构类问题的 section-aware retrieval 路由与观测字段。
- `evidence-policy-gate`: 新增结构化 claim 绑定优先门控，并禁止将列表编号、页码编号等格式性数字当作关键结论触发拒答。

## 影响

- 入库与解析：`app/ingest.py`、Marker 中间产物、chunk 元数据结构、可能新增 section 索引文件。
- 检索与问答：`app/qa.py`、`app/retrieve.py`、graph expansion 接入顺序、QA trace/report 字段。
- 输出治理：`answer_citations`、claim 绑定、Evidence Policy Gate 报告结构与低置信降级策略。
- 测试与评估：需要新增章节结构类问题样例、Marker 结构失败回退样例、门控假阳性回归样例。
