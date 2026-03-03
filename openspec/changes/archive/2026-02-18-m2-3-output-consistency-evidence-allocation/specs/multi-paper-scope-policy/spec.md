## 修改需求

### 需求:证据按论文分组输出
系统必须输出 `evidence_grouped`，并按论文分组展示证据。每篇论文最多展示 1~2 条 evidence；每条 quote 必须来自原始 `text` 字段，长度必须在 50~120 字之间。

#### 场景:跨论文命中时输出分组证据
- **当** top evidence 来自两篇或以上论文
- **那么** 系统必须按论文分组输出 evidence，并限制每篇显示条数为 1~2

### 需求:Scope Policy 指代不明处理
当问题命中指代词（如 this work/this paper/the authors/本文/这篇论文/作者）且缺少论文线索时，系统禁止默认假设某一篇论文。系统在执行跨论文模式时必须禁止向检索查询追加 `summary/in summary/overview/abstract overview/paper overview` 等 summary cue words，并必须进入意图校准流程生成 `calibrated_query`。

#### 场景:歧义问题禁用 summary cue
- **当** 问题命中指代词且未提供论文标识
- **那么** 系统必须从最终检索查询中排除 summary/overview/abstract 类 cue words

#### 场景:歧义问题生成校准查询
- **当** 问题命中指代词且采用跨论文检索模式
- **那么** 系统必须输出 `calibrated_query` 与可序列化 `calibration_reason`

## 新增需求

### 需求:rewrite_scope 回答必须跨论文聚合
当 `scope_mode=rewrite_scope` 时，系统禁止输出“单 chunk 指向式”回答，必须输出跨论文聚合回答；若证据可用，`answer_citations` 必须至少覆盖 2 个不同论文的 chunk。

#### 场景:rewrite_scope 的回答结构检查
- **当** 问题触发 rewrite_scope 且候选证据覆盖至少两篇论文
- **那么** 回答必须使用跨论文聚合表述，且 `answer_citations` 至少引用两篇不同论文

### 需求:open 模式单论文回答约束
当 `scope_mode=open` 且用户给出明确论文线索时，系统允许单论文回答，但 `answer_citations` 中所有引用必须属于同一 `paper_id`。

#### 场景:open 模式单论文引用一致
- **当** 用户在问题中明确指定单篇论文
- **那么** 回答引用的所有 chunk 必须来自同一论文，禁止跨论文混引
