## 为什么

当前 Python 链路中的 LLM 接入与供应商实现高度耦合：`provider` 与 `api_key` 判断存在硬编码，降级路径主要依赖特定供应商约定，导致切换模型供应商成本高、回归范围大、线上问题定位困难。现在需要在不新增部署服务的前提下，快速建立可配置的降级与可观测机制，为后续多模型与多供应商策略留出空间。

## 变更内容

- 在现有 Python 进程内引入 LiteLLM Python SDK，替换 `app/llm_client.py` 中手写的供应商请求实现。
- 保持现有调用接口与上层业务流程不变（`rewrite`/`qa` 调用路径尽量零感知），降低迁移风险。
- 将降级逻辑从“供应商硬编码”改为“基于错误类别与路由策略的统一 fallback/retry/cooldown”。
- 统一 LLM 调用可观测字段，覆盖模型选择、重试次数、fallback 原因、延迟与错误类别，并接入现有 runlog/diagnostics。
- 清理与供应商强绑定的配置校验与环境变量检查，改为按模型路由配置进行校验。

## 功能 (Capabilities)

### 新增功能
- `litellm-python-runtime-adapter`: 在 Python 运行时中提供基于 LiteLLM SDK 的统一 LLM 适配层，支持 completion/streaming 的一致返回契约。
- `llm-fallback-routing-policy`: 提供进程内可配置的 LLM fallback/retry/cooldown 路由策略，不依赖新增网关或代理服务。
- `llm-observability-contract`: 建立统一的 LLM 调用诊断与观测契约，覆盖 provider/model/fallback/attempt/latency/error。

### 修改功能
- `query-rewriting`: 将改写阶段 LLM 调用的降级判定迁移到统一策略层，移除供应商特定硬编码依赖。
- `llm-generation-foundation`: 将回答生成阶段的 LLM 调用与流式失败处理迁移到统一策略层，保持既有告警语义与回退行为。

## 影响

- 受影响代码：`app/llm_client.py`、`app/rewrite.py`、`app/qa.py`、`app/config.py`、`app/llm_diagnostics.py` 及相关测试。
- 受影响配置：LLM provider/api_key 校验规则与模型路由配置结构将调整。
- 兼容性：不引入新服务进程；目标是对现有上层业务接口与输出结构保持兼容。
- 风险点：迁移初期可能出现错误分类映射差异与 fallback 触发频率变化，需要通过回归测试与观测指标验证。
