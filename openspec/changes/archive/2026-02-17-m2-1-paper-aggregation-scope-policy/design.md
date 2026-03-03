## 上下文

当前 QA 流程基于 M2 检索结果直接输出 Top evidence，结构以“全局 top-k 列表”为中心。该方案在单论文问答可用，但在多论文知识库存在三类问题：
- 证据可解释性不足：用户难以判断答案由哪些论文支持；
- 指代语义歧义：`this work/本文/作者` 等提问在未指定论文时容易误解；
- 噪声证据干扰：`front_matter/reference` 可能在语义匹配中得高分并主导 Top 结果。

本变更需在不破坏既有 dense/bm25/hybrid 主链路的前提下，增加策略层与输出结构层能力。

## 目标 / 非目标

**目标：**
- 在 QA 输出与运行日志中新增 `scope_mode`、`query_used`、`papers_ranked`、`evidence_grouped`。
- 对候选 chunk 做论文级聚合，得到可追踪的论文排序结果。
- 引入 `front_matter/reference` 默认降权与条件放行策略，减少噪声主导。
- 对指代不明问题触发 `rewrite_scope` 或 `clarify_scope`，避免错误单篇假设。
- 为 M2.1 验收生成 `reports/m2_1_policy.md`。

**非目标：**
- 不在本阶段引入新检索后端（保持现有 BM25/FAISS 路径）。
- 不在本阶段引入 LLM 查询改写（`query_used` 允许先等于原问题）。
- 不追求复杂跨文档推理，仅实现策略可复现与输出可解释。

## 决策

### Decision 1: 在 `app/retrieve.py` 增加权重策略层而非重写召回器
- 方案：保持原召回逻辑，新增融合后分数修正函数：
  - 常量降权：`table_list *0.5`（沿用）
  - 默认降权：`front_matter/reference *0.3`
  - 条件放行：命中意图关键词时恢复或提升对应类型权重
- 原因：改动范围小、与现有测试兼容、可直接观测前后排序差异。
- 替代：在索引阶段剔除 `front_matter/reference`。
  - 放弃原因：会损失作者/机构/引用类问题的有效证据。

### Decision 2: 在 `app/qa.py` 增加 Scope Policy 前置判定
- 方案：在检索前做轻量规则判定：
  - 命中指代词且无论文线索 -> `rewrite_scope` 或 `clarify_scope`
  - 其余 -> `open`
- 原因：策略透明、可直接写入日志、便于后续替换为模型判定器。
- 替代：完全依赖用户补充上下文。
  - 放弃原因：体验中断明显，且无法满足规范要求的可追踪策略分流。

### Decision 3: 证据输出采用“先全局排序，再按 paper 分组截断”
- 方案：
  1. 获取全局候选排序；
  2. 计算 `papers_ranked`（`score_paper` 可取每篇 top chunk 的 max，辅以 mean 作为次序稳定器）；
  3. 构造 `evidence_grouped`，每篇最多 1~2 条。
- 原因：兼顾相关性与可读性，避免单篇论文占满 Top-5。
- 替代：先按 paper 平均切配再检索。
  - 放弃原因：会削弱高相关论文在当前问题下的优势。

### Decision 4: 运行日志字段与输出字段统一结构
- 方案：将 `question/mode/scope_mode/query_used/papers_ranked/evidence_grouped` 作为 QA 运行日志必填键，保证复现与评估脚本可复用。
- 原因：减少“终端输出”和“runs 记录”不一致导致的排查成本。

## 风险 / 权衡

- [风险] 关键词规则误判意图，导致放行或降权不准确
  → 缓解：关键词列表配置化；在报告中记录命中词与最终策略

- [风险] `rewrite_scope` 文案影响用户感知，可能被误解为拒答
  → 缓解：统一前缀提示并保留证据输出，确保是“改写视角”而非“中断”

- [风险] 论文分组后每篇仅 1~2 条 evidence 可能漏掉细节
  → 缓解：`papers_ranked.supporting_chunks` 保留更多候选（如 top 10）供追溯

## 迁移计划

1. 扩展 `retrieve` 的融合打分函数，接入 content_type 新策略。
2. 在 `qa` 增加 scope 判定、query_used 记录、paper 聚合与分组输出。
3. 更新 runlog 校验 schema，纳入 M2.1 新字段。
4. 更新/补充测试：
   - 指代词触发 `rewrite_scope/clarify_scope`
   - front_matter/reference 条件放行
   - evidence_grouped 结构与 quote 来源约束
5. 生成 `reports/m2_1_policy.md` 并完成抽检。

回滚策略：若新策略导致相关性显著下降，可临时关闭 front_matter/reference 默认降权与 scope 强制分流，仅保留字段输出骨架。

## 开放问题

- `score_paper` 最终采用 `max`、`mean` 还是 `max + lambda*mean`（需以 10+ 查询样本对比后定稿）。
- `rewrite_scope` 与 `clarify_scope` 的选择阈值是否仅规则化，还是引入更细粒度可解释特征（如 query 长度、实体命中数）。
- `peer_review` 是否作为新的噪声类型纳入默认降权（当前规范关注 front_matter/reference）。
