## ADDED Requirements

### 需求:回答阶段必须支持独立超时配置
系统必须支持回答阶段专用超时配置（例如 `answer_llm_timeout_ms`）；当该配置存在时必须优先于全局 `llm_timeout_ms` 生效。

#### 场景:回答阶段优先使用专用超时
- **当** 配置同时存在 `llm_timeout_ms` 与 `answer_llm_timeout_ms`
- **那么** `llm_answer` 调用必须使用 `answer_llm_timeout_ms`，并保持 rewrite 阶段使用原有超时策略

## MODIFIED Requirements

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

### 需求:LLM 调用失败不得中断主流程
任一 LLM 调用出现超时、限流、空响应、流式中断或解析失败时，系统必须将该次调用判定为失败并执行降级策略，禁止中断 QA 主链路。

#### 场景:调用异常时流程连续
- **当** LLM 调用返回超时、429、空文本、流式中断或结构化解析失败
- **那么** 系统必须返回可用回答结果（规则改写或模板回答），并保留失败告警与追踪信息

## REMOVED Requirements
