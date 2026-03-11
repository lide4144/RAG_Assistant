## 新增需求

### 需求:检索链路必须支持结构类问题路由
系统必须识别论文结构类问题，并在命中时优先使用章节树索引执行 structure-aware retrieval；当未命中结构类意图时，系统必须继续沿用既有摘要层与 chunk 层检索路径。

#### 场景:结构类问题进入 section route
- **当** 用户问题命中“章节/目录/结构/第几节”等结构类意图
- **那么** 系统必须将检索路由记录为 `section`，并优先使用 section index 召回候选

#### 场景:普通问题保持既有主路径
- **当** 用户问题不命中结构类意图
- **那么** 系统必须继续使用既有摘要层与 chunk 层检索，不得强制经过 section route

### 需求:结构检索必须输出可观测字段
当一次查询使用或尝试使用 structure-aware retrieval 时，系统必须记录结构检索观测字段，至少包括 `retrieval_route`、`structure_parse_status`、`section_candidates_count`、`section_route_used` 与 `structure_route_fallback`。

#### 场景:结构检索字段可追踪
- **当** 一次 QA 请求结束
- **那么** 运行日志与 QA 输出必须包含上述结构检索字段且字段可序列化

### 需求:section 候选必须补充 chunk 级证据
当 structure-aware retrieval 命中 section 候选时，系统必须将 section 关联 chunk 纳入候选组织、重排或证据分配流程。系统禁止只返回 section 标题而不补充 chunk 证据。

#### 场景:section 命中后补充 chunk evidence
- **当** section retrieval 返回章节候选
- **那么** 系统必须将该 section 的关联 chunk 纳入 evidence 组织，并保证最终 citation 仍指向 chunk

## 修改需求

### 需求:检索模式与融合
系统必须支持“三层检索”路径：基于 `paper_summary` 的候选文档粗召回、面向结构类问题的 section-aware retrieval、以及候选范围内的 chunk 检索与重排。系统必须支持在摘要层或结构层不可用时分别安全回退到既有 chunk 检索路径。

#### 场景:摘要层命中后进入候选文档精检索
- **当** 查询在 `paper_summary` 层返回候选文档
- **那么** 系统必须仅在候选文档范围执行 chunk 检索与重排并产出证据

#### 场景:结构层命中后进入章节精检索
- **当** 查询命中结构类意图且结构索引可用
- **那么** 系统必须先执行 section retrieval，再基于章节候选补充 chunk 证据并进入后续重排

#### 场景:摘要层不可用时安全回退
- **当** `paper_summary` 索引不可用或召回为空
- **那么** 系统必须回退至原有 chunk 检索路径并保持流程可用

#### 场景:结构层不可用时安全回退
- **当** 结构索引不可用、结构解析状态非 `ready` 或 section retrieval 为空
- **那么** 系统必须回退至 chunk 检索路径，并记录结构回退原因

## 移除需求
