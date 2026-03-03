## 为什么

当前 M2 检索在用户问题表达不稳定时容易召回波动：同义词、问句冗余、术语缩写会导致相关 chunk 排名不稳。M3 通过 Query Rewriting 先把问题变成“可检索表达”，在不引入复杂依赖的前提下提升召回稳定性与 evidence 相关性。

## 变更内容

- 新增 Query Rewriting 流程：输入问题 `Q`，输出改写查询 `Q'` 与 `keywords/entities`。
- 至少实现 3 类规则策略：
  - 术语保留（英文缩写、公式样式、关键指标如 accuracy/F1/BLEU）
  - 关键词扩展（同义/近义/领域词典）
  - 问句转检索句（去冗余保留核心）
- 将 rewrite 结果接入现有检索链路，支持开关控制；默认规则优先。
- 预留可选 LLM rewrite 开关（默认关闭），用于后续实验对比。
- 增加 M3 评估记录：对 M2 的 30 问题比较“改写前/后”召回主观表现，并记录至少 10 条 evidence 相关性改善样例。

## 功能 (Capabilities)

### 新增功能
- `query-rewriting`: 定义 `Q -> Q' + keywords/entities` 的产出结构、规则策略与开关行为。

### 修改功能
- `rag-baseline-retrieval`: 在检索链路中接入 rewrite 结果作为 query 输入，并记录改写相关运行字段。
- `pipeline-development-conventions`: 增补 M3 阶段运行日志与评估报告约定（含 rewrite 输入输出与效果记录）。

## 影响

- 受影响代码：`app/qa.py`、`app/retrieve.py`、新增 `app/rewrite.py`（或同等模块）。
- 受影响配置：`configs/default.yaml` 需加入 rewrite 开关与词典路径/策略参数。
- 受影响产物：`runs/*` 增加 rewrite 相关字段；新增 `reports/m3_rewrite_eval.md` 评估文档。
