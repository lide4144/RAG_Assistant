## 新增需求

### 需求:M2.1 策略评估记录
系统必须生成 `reports/m2_1_policy.md`，并至少记录 5 个“指代不明问题”的处理结果（rewrite 或 clarify）以及 5 个“作者/机构类问题”的条件放行验证结果。

#### 场景:完成 M2.1 评估后落盘
- **当** 用户完成 M2.1 策略评估
- **那么** 系统必须在 `reports/m2_1_policy.md` 写入不少于 10 条评估记录，并标注处理策略与证据摘要

## 修改需求

### 需求:运行日志字段完整性
系统必须在运行轨迹中记录以下字段：输入问题、rewrite 后 query、retrieval top-k 及分数、expansion 追加 chunk、rerank top-n 及分数、最终决策与回答。系统在 M2 QA 运行中还必须记录检索模式（dense/bm25/hybrid）与最终输出的 evidence 列表，以保证可复现性。系统在 M2.1 运行中必须额外记录 `scope_mode`、`query_used`、`papers_ranked`、`evidence_grouped`。

#### 场景:阶段性结果已产生
- **当** 检索与重排阶段产生候选结果
- **那么** 运行 JSON 必须包含 top-k/top-n 结果与对应分数字段

#### 场景:阶段尚未启用
- **当** 某运行尚未启用 retrieval、expansion 或 rerank 阶段
- **那么** 系统必须保留对应字段并写入空数组或 null，而不得省略字段

#### 场景:M2 QA 运行记录模式与证据
- **当** 用户执行 `python -m app.qa --q "..." --mode dense|bm25|hybrid`
- **那么** 运行日志必须记录本次检索模式与最终 evidence 列表

#### 场景:M2.1 运行记录聚合与范围策略
- **当** 用户执行 M2.1 策略下的 QA 运行
- **那么** 运行日志必须包含 `scope_mode`、`query_used`、`papers_ranked`、`evidence_grouped`

## 移除需求
