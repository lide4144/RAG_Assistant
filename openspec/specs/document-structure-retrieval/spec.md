# document-structure-retrieval 规范

## 目的
定义基于 PDF 结构化解析结果的章节树检索能力，确保系统能够对目录、章节与结构类问题提供可追溯的 section-aware retrieval。

## 需求
### 需求:系统必须构建可检索的章节树索引
系统必须基于 PDF 结构化解析结果构建章节树索引，至少包含 `section_id`、`paper_id`、`section_title`、`section_level`、`heading_path`、`start_page`、`end_page` 与 `child_chunk_ids`。系统必须保证 section 与 chunk 的映射可追溯，禁止生成无法回溯到 chunk 的孤立章节节点。

#### 场景:章节树索引构建成功
- **当** 一篇论文的 Marker 结构解析结果可用且标题层级通过质量门禁
- **那么** 系统必须为该论文产出可检索的章节树索引，并记录每个 section 对应的 chunk 映射

#### 场景:章节节点不可回溯时拒绝入索引
- **当** 某 section 无法映射到任何有效 `child_chunk_ids`
- **那么** 系统必须拒绝将该 section 写入可检索索引，并记录结构不完整告警

### 需求:系统必须对结构类问题优先使用章节检索
当用户问题命中“章节/目录/结构/第几节”等结构类意图时，系统必须优先执行章节检索并返回相关 section 候选；在结构候选存在时，系统禁止直接跳过 section retrieval 仅使用普通 chunk 检索。

#### 场景:章节类问题命中结构路由
- **当** 用户问题包含“多少个章节”“目录”“第 3.1 节”“论文结构”等结构类意图
- **那么** 系统必须优先检索 section index，并在运行日志中记录 `retrieval_route=section`

#### 场景:结构候选命中后补充 chunk 证据
- **当** section retrieval 返回相关章节
- **那么** 系统必须基于 `child_chunk_ids` 或章节邻接 chunk 补充 chunk 级证据，供最终回答与引用使用

### 需求:结构检索失败时必须显式降级
当章节树索引不存在、结构解析状态非 `ready`、或 structure retrieval 结果为空时，系统必须显式降级到既有 chunk 检索路径，并记录降级原因；系统禁止静默假装已完成结构检索。

#### 场景:文档结构不可解析时降级
- **当** 结构解析状态为 `degraded` 或 `unavailable`
- **那么** 系统必须回退到 chunk 检索，并记录 `structure_route_fallback=structure_unavailable`

#### 场景:结构检索空结果时降级
- **当** 用户问题命中结构路由但 section retrieval 返回空结果
- **那么** 系统必须回退到 chunk 检索，并记录 `structure_route_fallback=section_retrieval_empty`

### 需求:结构类回答必须披露覆盖边界
当结构类问题仅命中局部 section 或结构解析状态非完整可用时，系统必须在回答或运行报告中明确披露覆盖边界，禁止将局部章节证据表述为完整目录结论。

#### 场景:仅命中局部章节时低置信说明
- **当** 结构类问题仅召回部分章节而非完整章节树
- **那么** 系统必须明确说明“当前仅基于局部章节证据”，不得输出“全文共有 N 章”这类完整断言
