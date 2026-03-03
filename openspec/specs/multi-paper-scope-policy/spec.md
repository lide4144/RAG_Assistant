# multi-paper-scope-policy 规范

## 目的
待定 - 由归档变更 m2-1-paper-aggregation-scope-policy 创建。归档后请更新目的。
## 需求
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
当问题命中指代词且缺少论文线索时，系统禁止默认假设某一篇论文。在触发 `clarify` 决策后，下一轮必须先执行“上一轮原始问题 + 系统澄清问题 + 用户补充”的合并，再进入检索链路，禁止直接使用用户短答独立检索。

#### 场景:clarify 后短答闭环
- **当** 上一轮最终决策为 `need_scope_clarification` 且本轮用户仅提供短线索（如“作者是何恺明那篇”）
- **那么** 系统必须先生成合并后的独立问题再检索，并避免再次进入同一澄清循环

### 需求:意图驱动 cue words 校准
系统必须基于问题意图向 `calibrated_query` 追加语义目标 cue words。至少支持 limitation、contribution、dataset、metric 四类意图，并为每类提供中英文 cue words 追加策略。

#### 场景:limitation 意图追加
- **当** 问题命中“局限/不足/缺点/限制/future work/limitation”等词
- **那么** 系统必须向 `calibrated_query` 追加 limitation 相关中英文 cue words

#### 场景:dataset 或 metric 意图追加
- **当** 问题命中“数据集/benchmark/metric/准确率/F1”等词
- **那么** 系统必须向 `calibrated_query` 追加对应 dataset 或 metric 的中英文 cue words

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

