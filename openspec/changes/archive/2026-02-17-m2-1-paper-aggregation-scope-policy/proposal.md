## 为什么

当前 M2 基线已能返回 evidence，但多论文场景下仍存在三个问题：
1) Top evidence 易被 front_matter/reference 等噪声内容主导；
2) 指代不明问题（如“this work/本文/作者”）会被错误地默认为单篇论文；
3) 输出缺少按论文聚合结构，难以复现与人工审阅。

M2.1 旨在把“单候选列表”升级为“多论文聚合 + scope policy + 分组证据输出”，让个人论文知识库问答在多文档语境下更稳健、更可解释。

## 变更内容

- 在 QA 输出与运行记录中新增并强制记录字段：`scope_mode`、`query_used`、`papers_ranked`、`evidence_grouped`。
- 新增 paper 聚合逻辑：将候选 chunks 按 `paper_id` 聚合，计算 `score_paper`，并输出 `supporting_chunks`。
- 新增分组证据输出：按论文展示 evidence，每篇最多 1~2 条，quote 必须来自原始 `text`（50~120 字）。
- 引入 content_type 权重策略：
  - 继续排除 `watermark`，继续降权 `table_list`；
  - 默认降权 `front_matter`、`reference`；
  - 按 query 意图进行条件放行（作者机构意图、引用出处意图）。
- 新增 Scope Policy：对“this work/本文/作者”等指代不明问题，在缺少论文线索时触发 `rewrite_scope` 或 `clarify_scope`，禁止隐式假设单篇论文。
- 增加 M2.1 评估报告要求：`reports/m2_1_policy.md`（5 个指代问题 + 5 个作者机构问题）。

## 功能 (Capabilities)

### 新增功能
- `multi-paper-scope-policy`: 定义跨论文聚合检索、scope 判定策略与分组证据输出结构。

### 修改功能
- `rag-baseline-retrieval`: 扩展 QA 输出字段与 evidence 展示规则，加入按 paper 聚合与分组输出。
- `pipeline-development-conventions`: 增补 M2.1 运行记录字段与评估报告落盘要求，确保可复现。

## 影响

- 受影响代码：`app/retrieve.py`、`app/qa.py`、可能新增/调整 policy 与 aggregation 相关模块。
- 受影响数据：`runs/YYYYMMDD_HHMM*/` 运行日志结构将新增字段；`reports/m2_1_policy.md` 将成为阶段验收产物。
- 受影响行为：检索排序会因 content_type 降权与条件放行发生变化；回答前置策略会在指代不明时转为 rewrite/clarify。
