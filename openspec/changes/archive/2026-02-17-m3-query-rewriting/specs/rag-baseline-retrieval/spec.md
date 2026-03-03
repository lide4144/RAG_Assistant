## 新增需求

## 修改需求

### 需求:最小 QA CLI 输出
系统必须提供命令 `python -m app.qa --q "<question>" --mode dense|bm25|hybrid`。命令输出必须包含 Answer 与 evidence，且运行记录必须包含字段：`question`、`mode`、`scope_mode`、`query_used`、`papers_ranked`、`evidence_grouped`。在 M3 中，`query_used` 必须记录实际检索查询（可为 `Q'`），并在启用 rewrite 时与原问题可区分。

#### 场景:CLI 问答输出字段完整
- **当** 用户执行 QA CLI 并获得候选证据
- **那么** 系统必须输出上述必需字段，并保证 `evidence_grouped` 按论文分组

#### 场景:启用 rewrite 时记录 Q 与 Q'
- **当** 用户启用改写流程并执行检索
- **那么** 运行输出必须可区分原问题 `Q` 与检索查询 `Q'`

### 需求:M2 最小验收
系统必须满足 M2 基线验收：dense 与 bm25 都能返回 top-k，hybrid 能返回融合结果；并对至少 30 个自制问题可在 evidence 中找到相关段落（主观评审）。在 M3 中，接入 rewrite 后 Recall@k 主观效果相较未改写不得下降，且至少 10 个问题 evidence 相关性应更高。

#### 场景:检索模式验收
- **当** 对同一问题分别执行 `dense`、`bm25`、`hybrid`
- **那么** 系统必须在三种模式下都返回非空候选，且 `hybrid` 返回融合排序结果

#### 场景:M3 对比评估
- **当** 在同一 30 问题集合上比较“改写前”与“改写后”
- **那么** 主观 Recall@k 不得下降，且至少 10 个问题 evidence 更相关

## 移除需求
