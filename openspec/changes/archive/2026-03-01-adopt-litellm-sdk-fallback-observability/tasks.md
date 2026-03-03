## 1. LiteLLM 适配层落地

- [x] 1.1 在 `app/llm_client.py` 引入 LiteLLM SDK 并保留现有调用函数签名与返回结构
- [x] 1.2 完成非流式调用替换并映射 `status_code/reason/attempts_used/elapsed_ms`
- [x] 1.3 完成流式调用替换并对齐 `first_token_latency_ms/chunks_received/stream_events`
- [x] 1.4 增加适配层单测，覆盖成功、空响应、超时、限流、网络错误场景

## 2. 统一 fallback 路由策略

- [x] 2.1 引入进程内 Router 配置结构（主模型、备模型、retry、cooldown）
- [x] 2.2 实现错误类别到 fallback 策略的映射（timeout/429/5xx/network）
- [x] 2.3 在 rewrite 与 answer 两个阶段接入统一路由策略
- [x] 2.4 增加 fallback 行为测试，验证主失败备成功与冷却窗口行为

## 3. 可观测性与诊断契约

- [x] 3.1 定义并实现统一观测字段（provider_used/model_used/attempts/fallback_reason/elapsed_ms）
- [x] 3.2 将流式指标（first_token/chunks）接入现有 diagnostics 与 runlog
- [x] 3.3 接入 LiteLLM callback 并确保成功/失败/降级路径均有记录
- [x] 3.4 增加 runlog 合规测试，验证新字段与既有 warning 口径兼容

## 4. 配置与兼容迁移

- [x] 4.1 将 `app/config.py` 的 LLM 校验从单一 `SILICONFLOW_API_KEY` 检查改为路由配置校验
- [x] 4.2 设计并落地主备模型配置字段，支持 OpenAI-compatible `api_base`/`api_key_env`
- [x] 4.3 保留迁移期回退开关，支持切回旧调用路径
- [x] 4.4 补充配置验证测试与错误提示测试

## 5. 回归与发布保障

- [x] 5.1 回归 `tests/test_rewrite.py` 与 `tests/test_m2_retrieval_qa.py` 的核心 LLM fallback 用例
- [x] 5.2 回归流式与首 token 相关测试，确保性能指标字段持续可用
- [x] 5.3 建立迁移对比报告（fallback 触发率、平均延迟、错误分布）
- [x] 5.4 完成灰度启用与回滚演练记录
