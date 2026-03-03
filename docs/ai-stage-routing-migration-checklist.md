# AI Stage Routing 迁移检查清单

适用于 `answer / embedding / rerank` 三阶段统一路由改造后的上线检查。

## 1. 配置迁移

- [ ] `configs/default.yaml` 已包含 `embedding_*` 与 `rerank_*` stage 前缀字段。
- [ ] 旧配置（`embedding.*`、`rerank.*`）在未迁移时仍可启动并被兼容映射。
- [ ] 生产环境已明确设置：
  - [ ] `embedding_api_key_env`
  - [ ] `rerank_api_key_env`
  - [ ] `answer_llm_api_key_env`

## 2. 路由与降级验证

- [ ] embedding key 缺失时，检索可自动回退到 TF-IDF/BM25。
- [ ] rerank 超时/5xx/网络错误时，系统进入静默穿透（沿用检索序）。
- [ ] rerank 穿透时候选仍包含 `score_rerank`（默认等于 `score_retrieval`）。

## 3. 健康检查

- [ ] `GET /health/deps` 可返回 `answer/embedding/rerank` 三路状态对象。
- [ ] embedding 维度异常可在 `reason` 中观测到 `dimension_mismatch`。
- [ ] rerank 穿透可观测 `passthrough_mode=true` 和最近失败原因。

## 4. 兼容性回归

- [ ] 旧嵌套配置键仍可运行。
- [ ] 新旧键并存时，确认优先级符合预期（新 stage 前缀优先）。
- [ ] e2e 回归确认回答链路不被单 stage 故障拖垮。

## 5. 后续弃用计划（建议）

1. 观察期 1-2 个发布周期，仅记录旧键使用告警，不阻断。
2. 观察期结束后在文档与启动日志中标记旧键为 deprecated。
3. 下一个大版本移除旧键解析逻辑，保留一次自动迁移脚本。
