## 新增需求

### 需求:M3 改写评估记录
系统必须生成 `reports/m3_rewrite_eval.md`，至少记录 30 个问题在“改写前/改写后”的检索对比结论，并明确标注至少 10 个问题 evidence 相关性提升样例。

#### 场景:完成 M3 评估后落盘
- **当** 用户完成 M3 rewrite 评估
- **那么** 系统必须在 `reports/m3_rewrite_eval.md` 写入对比记录与改进样例

## 修改需求

### 需求:运行日志字段完整性
系统必须在运行轨迹中记录以下字段：输入问题、rewrite 后 query、retrieval top-k 及分数、expansion 追加 chunk、rerank top-n 及分数、最终决策与回答。系统在 M2 QA 运行中还必须记录检索模式（dense/bm25/hybrid）与最终输出的 evidence 列表，以保证可复现性。系统在 M2.1 运行中必须额外记录 `scope_mode`、`query_used`、`papers_ranked`、`evidence_grouped`。在 M3 中，系统还必须记录 rewrite 策略命中信息与 `keywords/entities`。

#### 场景:阶段性结果已产生
- **当** 检索与重排阶段产生候选结果
- **那么** 运行 JSON 必须包含 top-k/top-n 结果与对应分数字段

#### 场景:阶段尚未启用
- **当** 某运行尚未启用 retrieval、expansion 或 rerank 阶段
- **那么** 系统必须保留对应字段并写入空数组或 null，而不得省略字段

#### 场景:M2 QA 运行记录模式与证据
- **当** 用户执行 `python -m app.qa --q "..." --mode dense|bm25|hybrid`
- **那么** 运行日志必须记录本次检索模式与最终 evidence 列表

#### 场景:M3 运行记录改写细节
- **当** 用户执行启用 rewrite 的 QA 运行
- **那么** 运行日志必须包含 `Q`、`Q'`、rewrite 策略命中结果与 `keywords/entities`

## 移除需求
