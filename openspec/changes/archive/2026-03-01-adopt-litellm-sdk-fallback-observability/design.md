## 上下文

当前 `app/llm_client.py` 通过供应商分支拼接 endpoint，并在 `rewrite/qa/config` 中存在 `SILICONFLOW_API_KEY` 级别的硬编码依赖。该模式在“单供应商可运行”场景下成本低，但在多供应商切换、统一降级策略与故障可观测方面存在明显扩展瓶颈。约束条件是：不引入新的网关或代理服务，必须在现有 Python 进程内完成迁移，并尽量保持上层调用接口与回归测试稳定。

## 目标 / 非目标

**目标：**
- 在 Python 进程内引入 LiteLLM SDK，替换手写 HTTP 调用并保留现有 `llm_client` 对外接口。
- 将 fallback/retry/cooldown 策略集中到统一路由层，避免业务代码散布供应商判断。
- 将 LLM 观测字段标准化并接入现有 diagnostics/runlog。
- 在不新增服务部署的前提下，支持主模型失败自动降级到备模型。

**非目标：**
- 不引入 LiteLLM Proxy 或新增独立服务进程。
- 不在本次变更中重构 rewrite/sufficiency/answer 的业务语义策略。
- 不一次性重写全部配置系统，仅扩展 LLM 相关配置结构。

## 决策

### 决策 1：保留 `llm_client` 作为防腐层，内部替换为 LiteLLM SDK
- 方案 A（采纳）：仅替换 `llm_client` 内部实现，`rewrite.py` 与 `qa.py` 继续调用现有函数。
- 方案 B（未采纳）：在 `rewrite/qa` 直接调用 LiteLLM。
- 原因：A 能最大限度控制改动面与回归风险，保持现有诊断对象结构稳定。

### 决策 2：采用自研进程内 Router 策略管理 fallback/retry/cooldown
- 方案 A（采纳）：使用自研进程内 Router（Custom Router）维护模型路由与降级，并在调用执行层使用 `litellm.completion`。
- 方案 B（未采纳）：保留现有散落的 try/except + warning 映射。
- 原因：A 将“策略”与“业务”解耦，后续扩展供应商无需修改上层业务逻辑。

### 决策 3：错误语义统一映射到现有 warning 契约
- 方案 A（采纳）：新增错误类别映射层，把 LiteLLM 异常映射到既有 warning（如 timeout/rate_limit/empty_response）。
- 方案 B（未采纳）：直接把 LiteLLM 原始异常暴露到上层。
- 原因：A 兼容现有测试与报表口径，迁移期间可稳定比对前后行为。

### 决策 4：配置从“单 key 硬编码检查”转为“模型路由配置校验”
- 方案 A（采纳）：按 model route 校验 api key/env、api_base、优先级与 fallback 列表完整性。
- 方案 B（未采纳）：继续在 config 中仅检查 `SILICONFLOW_API_KEY`。
- 原因：A 可移除供应商绑定并支持多模型路由。

### 决策 5：可观测性采用本地事件回调总线 + diagnostics 双通道
- 方案 A（采纳）：使用本地事件回调总线捕获调用事件，并将关键字段写入现有 diagnostics/runlog。
- 方案 B（未采纳）：仅在异常分支手写日志。
- 原因：A 能统一成功/失败/降级路径的观测口径，便于回归分析。

## 风险 / 权衡

- [风险] LiteLLM 异常类型与现有 warning 语义不完全一致。  
  -> 缓解：建立显式错误映射表并补充映射单测。

- [风险] fallback 触发条件变化导致线上行为波动。  
  -> 缓解：保留旧策略开关并支持按配置回退到旧调用路径。

- [风险] 流式响应事件格式差异影响首 token 统计。  
  -> 缓解：在 `llm_client` 层统一 first_token/chunk 统计与结构化输出。

- [风险] 配置复杂度上升导致错误配置率增加。  
  -> 缓解：启动时执行路由配置验证并给出可读告警。

## Migration Plan

1. 在 `llm_client` 中引入 LiteLLM 但保留旧函数签名与返回结构。
2. 实现非流式调用替换与错误映射，确保 rewrite 路径通过回归。
3. 实现流式调用替换并校准 first token/chunk 观测字段。
4. 接入 Router fallback/retry/cooldown，配置主备模型并完成失败演练。
5. 接入 callback 到 diagnostics/runlog，验证观测字段完整性。
6. 移除 `SILICONFLOW_API_KEY` 硬编码校验，切换为路由配置校验。

回滚策略：
- 通过配置开关切回旧调用分支（保留旧实现窗口期）；
- 回滚失败时恢复上一版本配置与 `llm_client` 实现。

## Open Questions

- SiliconFlow 在当前 LiteLLM 版本中是否采用 OpenAI-compatible 路由即可满足流式与错误语义需求？
- fallback 策略应按 stage（rewrite/answer）分别配置，还是共享同一 Router 组？
- callback 写入 runlog 的字段边界应保持最小兼容，还是同步扩展 token/cost 统计字段？
