## 新增需求

### 需求:论文级聚合排序
系统必须将检索候选按 `paper_id` 聚合并输出 `papers_ranked`。`papers_ranked` 必须为 `list[{paper_id, paper_title, score_paper, supporting_chunks}]`，且 `supporting_chunks` 至少包含该论文进入候选集合的 chunk_id（可截断到 top 10）。

#### 场景:生成 paper 聚合结果
- **当** QA 检索阶段得到 top-k 候选 chunks
- **那么** 系统必须按论文输出 `papers_ranked`，并为每篇论文计算 `score_paper`

### 需求:证据按论文分组输出
系统必须输出 `evidence_grouped`，并按论文分组展示证据。每篇论文最多展示 1~2 条 evidence；每条 quote 必须来自原始 `text` 字段，长度必须在 50~120 字之间。

#### 场景:跨论文命中时输出分组证据
- **当** top evidence 来自两篇或以上论文
- **那么** 系统必须按论文分组输出 evidence，并限制每篇显示条数为 1~2

### 需求:Scope Policy 指代不明处理
当问题命中指代词（如 this work/this paper/the authors/本文/这篇论文/作者）且缺少论文线索时，系统禁止默认假设某一篇论文，必须触发 `rewrite_scope` 或 `clarify_scope` 二选一策略。

#### 场景:触发 rewrite_scope
- **当** 问题包含指代词且未提供论文标识，但系统可进行跨论文总结
- **那么** 系统必须将 `scope_mode` 设为 `rewrite_scope`，并在 Answer 开头提示“未指定具体论文，以下为知识库相关论文的综合证据”

#### 场景:触发 clarify_scope
- **当** 问题包含指代词且无法可靠执行跨论文总结
- **那么** 系统必须将 `scope_mode` 设为 `clarify_scope`，并要求用户补充论文标题/作者/年份/会议线索

## 修改需求

## 移除需求
