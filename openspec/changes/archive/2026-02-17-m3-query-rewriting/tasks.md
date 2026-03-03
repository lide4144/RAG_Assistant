## 1. Rewrite 模块与配置

- [x] 1.1 新增 `app/rewrite.py`，定义 `RewriteResult(Q, Q', keywords/entities, strategy_hits)` 数据结构与主入口函数
- [x] 1.2 实现术语保留规则（英文缩写、公式样式、数字指标）并补单元测试
- [x] 1.3 实现关键词扩展规则（同义/近义/领域词典）并补单元测试
- [x] 1.4 实现问句转检索句规则（去冗余保核心）并补单元测试
- [x] 1.5 在 `configs/default.yaml` 增加 rewrite 开关与参数（含可选 LLM rewrite 开关，默认关闭）

## 2. 检索链路接入

- [x] 2.1 在 `app/qa.py` 接入 rewrite：保留 `question=Q`，并将 `query_used=Q'` 传入检索
- [x] 2.2 在运行日志与报告中记录 `Q`、`Q'`、`keywords/entities`、`strategy_hits`
- [x] 2.3 保持 dense/bm25/hybrid 三模式行为不回退，补回归测试

## 3. 评估与验收

- [x] 3.1 构建 30 问题“改写前/后”对比脚本或流程，记录 Recall@k 主观对比结果
- [x] 3.2 输出 `reports/m3_rewrite_eval.md`，至少包含 10 个 evidence 相关性提升样例
- [x] 3.3 增加可选 LLM rewrite 开关测试（关闭默认、开启路径可运行或可降级）
