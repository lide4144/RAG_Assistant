## 1. 配置模型统一化

- [x] 1.1 在 `app/config.py` 增加 stage 前缀配置族（`answer_*`、`embedding_*`、`rerank_*`）并补充类型校验
- [x] 1.2 在 `configs/default.yaml` 与相关示例配置中新增 `embedding_`、`rerank_` 路由字段并提供兼容默认值
- [x] 1.3 实现旧配置键（`embedding.*`、`rerank.*`）到新 stage 配置的兼容映射与优先级规则
- [x] 1.4 增加配置缺失/非法场景测试，验证单 stage 失败不会拖垮其他 stage

## 2. 路由中心改造

- [x] 2.1 将 `app/llm_routing.py` 升级为统一 AI 路由中心，支持 `stage=answer|embedding|rerank`
- [x] 2.2 在路由中心实现统一失败分类（`missing_api_key`、`timeout`、`network_error`、`server_error`、`dimension_mismatch`）
- [x] 2.3 为路由中心增加阶段级降级信号接口，供检索与重排链路消费
- [x] 2.4 为路由中心补充单元测试，覆盖三 stage 的解析与失败分类

## 3. Embedding 降级与维度守卫

- [x] 3.1 在 embedding 调用链路接入 stage 路由配置，移除 `SILICONFLOW_API_KEY` 唯一依赖
- [x] 3.2 增加 embedding 维度一致性检查（主模型、备用模型、索引维度）并在不一致时阻断向量检索
- [x] 3.3 实现 embedding 重试耗尽后的 TF-IDF/BM25 静默降级路径
- [x] 3.4 在无法降级场景抛出结构化不可恢复异常，并在上层可识别处理
- [x] 3.5 增加检索日志字段，记录 embedding 降级原因与是否回退成功

## 4. Rerank 静默穿透与结构兼容

- [x] 4.1 在 `app/rerank.py` 接入 stage 路由，统一超时/5xx/网络失败处理
- [x] 4.2 实现 rerank 失败静默穿透：直接沿用上游候选顺序
- [x] 4.3 在穿透路径补齐兼容字段（至少 `score_rerank`，默认复用 `score_retrieval`）
- [x] 4.4 增加 `used_fallback`/`rerank_fallback_to_retrieval` 等观测标记并补充测试

## 5. 健康检查与可观测性

- [x] 5.1 在 `app/kernel_api.py` 新增 `/health/deps` 路由并返回 answer/embedding/rerank 三路状态
- [x] 5.2 为 `/health/deps` 增加 embedding 维度不一致诊断输出（`dimension_mismatch`）
- [x] 5.3 为 `/health/deps` 增加 rerank 穿透状态输出（如 `passthrough_mode` 与最近失败原因）
- [x] 5.4 为健康接口补充契约测试与错误分支测试

## 6. 端到端验证与迁移收敛

- [x] 6.1 增加 e2e 用例：embedding key 缺失时自动回退词频检索且回答链路可用
- [x] 6.2 增加 e2e 用例：rerank 超时时静默穿透且下游 `qa` 不因字段缺失报错
- [x] 6.3 更新运维文档，说明新配置优先级、降级语义与 `/health/deps` 使用方式
- [x] 6.4 输出迁移检查清单，确认旧配置仍可兼容并给出后续弃用计划
