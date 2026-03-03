# llm-generation-foundation 规范

## 目的
待定 - 由归档变更 m7-5-llm-generation-foundation 创建。归档后请更新目的。
## 需求
### 需求:统一 LLM 提供方与模型配置
系统必须支持独立的 rewrite/answer LLM 配置，并提供默认值：
- `rewrite_llm_provider=siliconflow`
- `rewrite_llm_model=Pro/deepseek-ai/DeepSeek-V3.2`
- `answer_llm_provider=siliconflow`
- `answer_llm_model=Pro/deepseek-ai/DeepSeek-V3.2`
并且必须支持 `llm_timeout_ms`、`llm_max_retries`、`llm_fallback_enabled`、`answer_stream_enabled`，以及回答阶段专用超时配置。

#### 场景:默认配置可加载
- **当** 用户未覆盖 LLM 相关配置
- **那么** 系统必须加载默认 provider/model，保留全局超时重试配置，并将回答流式开关置为安全默认值

### 需求:统一 LLM 鉴权与降级前置检查
系统必须通过环境变量 `SILICONFLOW_API_KEY` 进行鉴权；当开关开启但缺少鉴权信息时，系统必须记录降级原因并继续主流程，禁止抛出中断性错误。

#### 场景:缺少 API Key 自动降级
- **当** `rewrite_use_llm=true` 或 `answer_use_llm=true` 且 `SILICONFLOW_API_KEY` 为空
- **那么** 系统必须跳过 LLM 调用并进入规则/模板路径，且运行日志必须包含可追踪降级原因

### 需求:LLM 调用失败不得中断主流程
任一 LLM 调用出现超时、限流、空响应、流式中断或解析失败时，系统必须将该次调用判定为失败并执行降级策略，禁止中断 QA 主链路。

#### 场景:调用异常时流程连续
- **当** LLM 调用返回超时、429、空文本、流式中断或结构化解析失败
- **那么** 系统必须返回可用回答结果（规则改写或模板回答），并保留失败告警与追踪信息

### 需求:M7.5 评估报告必须落盘
系统必须提供 M7.5 rewrite 与 answer 两类评估报告，路径固定为：
- `reports/m7_5_llm_rewrite_eval.md`
- `reports/m7_5_llm_answer_eval.md`

#### 场景:评估完成后可审计
- **当** 执行 M7.5 验收评估流程
- **那么** 系统必须在上述固定路径生成可读报告，包含样本规模、通过率与失败样本摘要

### 需求:回答阶段必须支持独立超时配置
系统必须支持回答阶段专用超时配置（例如 `answer_llm_timeout_ms`）；当该配置存在时必须优先于全局 `llm_timeout_ms` 生效。

#### 场景:回答阶段优先使用专用超时
- **当** 配置同时存在 `llm_timeout_ms` 与 `answer_llm_timeout_ms`
- **那么** `llm_answer` 调用必须使用 `answer_llm_timeout_ms`，并保持 rewrite 阶段使用原有超时策略

### 需求:系统必须采用答案规划与证据绑定两段式生成
回答生成必须先形成可验证结论单元（claims），再进行 claim-citation 绑定，最后渲染为用户可读答案；禁止跳过证据绑定直接生成最终自然语言回答。

#### 场景:claim 绑定成功后输出答案
- **当** claim 与证据绑定完成
- **那么** 系统必须输出包含引用标记的自然语言答案，且每条关键结论可追溯

### 需求:系统必须将可读性与可追溯性同时纳入输出约束
回答 prompt 必须同时约束“证据内回答”与“用户可读表达”，禁止仅输出模板化低信息密度文本。

#### 场景:证据充分时输出结构化高信息回答
- **当** 证据覆盖关键问题
- **那么** 系统必须输出包含结论、依据与不确定性边界的结构化回答

### 需求:系统必须在答案生成阶段维持统一降级与诊断契约
系统必须将答案生成阶段的非流式与流式调用统一纳入路由策略，保持现有 fallback warning 与诊断字段语义稳定。

#### 场景:流式中断后保持兼容回退语义
- **当** 流式回答过程发生中断或空响应
- **那么** 系统必须返回与既有行为兼容的 fallback warning，并写入标准化诊断字段

### 需求:系统必须将模型选择与调用结果写入可观测数据
系统必须为答案生成记录最终使用模型、尝试次数、首 token 延迟与 fallback 原因，以支持回归与故障分析。

#### 场景:主模型失败后备模型成功
- **当** 主模型失败且备模型成功返回答案
- **那么** 系统必须在诊断中同时记录失败原因与最终成功模型

