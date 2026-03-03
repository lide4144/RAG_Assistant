## 1. Rerank 配置与契约校验

- [x] 1.1 在 `configs/default.yaml` 增加 rerank 配置：`enabled`、`top_n`（默认 8）、provider/model、timeout、retry/fallback 选项
- [x] 1.2 在 `app/config.py` 增加配置解析与默认值校验，确保 top_n 为正整数
- [x] 1.3 在 rerank 入口增加候选字段契约校验：`score_retrieval`、`payload.source`、`payload.dense_backend` 必填
- [x] 1.4 增加 embedding 路径的字段校验：`payload.embedding_provider` 与 `payload.embedding_model` 缺失时触发受控降级/告警

## 2. Rerank 核心实现与链路接入

- [x] 2.1 在 `app/rerank.py` 实现统一 rerank 接口，输入 `candidates + query`，输出含 `score_rerank` 的候选
- [x] 2.2 实现 SiliconFlow `Qwen/Qwen3-Reranker-8B` provider 适配，并保留 provider 抽象以支持后续替换
- [x] 2.3 实现 rerank 排序与 top_n 截断逻辑，保证同时保留 `score_retrieval` 与 `payload` 字段
- [x] 2.4 在 `app/qa.py` 接入“候选 -> rerank -> evidence 组织”流程，并在 rerank 不可用时回退到 `score_retrieval` 排序
- [x] 2.5 增加断言/测试确保 rerank 前后 `payload.dense_backend` 不发生改写

## 3. 运行日志与可观测性

- [x] 3.1 在 `app/runlog.py`（或等效路径）新增 `rerank_top_n`、`rerank_score_distribution`、`dense_backend` 落盘
- [x] 3.2 确保 embedding 模式下日志继续完整记录既有 embedding 字段，并与 rerank 字段同时可序列化
- [x] 3.3 在 QA 输出或 warning 中增加 rerank 失败降级标记，便于追踪回退路径

## 4. 测试、评估与验收报告

- [x] 4.1 新增单测：字段契约校验、top_n 默认值、`score_rerank` 生成与保留 `score_retrieval`
- [x] 4.2 新增集成测试：dense/bm25/hybrid + graph expansion 场景下 rerank 输出稳定且字段完整
- [x] 4.3 准备 20 个问题对比样例，人工核验 rerank 后 top3 相关性提升或更稳定
- [x] 4.4 产出 `reports/m6_rerank.md`，记录 rerank 前后对比样例、分布统计与结论
