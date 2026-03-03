## ADDED Requirements

### 需求:统一 LLM 提供方与模型配置
系统必须支持独立的 rewrite/answer LLM 配置，并提供默认值：
- `rewrite_llm_provider=siliconflow`
- `rewrite_llm_model=Pro/deepseek-ai/DeepSeek-V3.2`
- `answer_llm_provider=siliconflow`
- `answer_llm_model=Pro/deepseek-ai/DeepSeek-V3.2`
并且必须支持 `llm_timeout_ms`、`llm_max_retries`、`llm_fallback_enabled`。

#### 场景:默认配置可加载
- **当** 用户未覆盖 LLM 相关配置
- **那么** 系统必须加载上述默认 provider/model 与通用超时重试配置

### 需求:统一 LLM 鉴权与降级前置检查
系统必须通过环境变量 `SILICONFLOW_API_KEY` 进行鉴权；当开关开启但缺少鉴权信息时，系统必须记录降级原因并继续主流程，禁止抛出中断性错误。

#### 场景:缺少 API Key 自动降级
- **当** `rewrite_use_llm=true` 或 `answer_use_llm=true` 且 `SILICONFLOW_API_KEY` 为空
- **那么** 系统必须跳过 LLM 调用并进入规则/模板路径，且运行日志必须包含可追踪降级原因

### 需求:LLM 调用失败不得中断主流程
任一 LLM 调用出现超时、限流、空响应或解析失败时，系统必须将该次调用判定为失败并执行降级策略，禁止中断 QA 主链路。

#### 场景:调用异常时流程连续
- **当** LLM 调用返回超时、429、空文本或结构化解析失败
- **那么** 系统必须返回可用回答结果（规则改写或模板回答），并保留失败告警与追踪信息

### 需求:M7.5 评估报告必须落盘
系统必须提供 M7.5 rewrite 与 answer 两类评估报告，路径固定为：
- `reports/m7_5_llm_rewrite_eval.md`
- `reports/m7_5_llm_answer_eval.md`

#### 场景:评估完成后可审计
- **当** 执行 M7.5 验收评估流程
- **那么** 系统必须在上述固定路径生成可读报告，包含样本规模、通过率与失败样本摘要

## MODIFIED Requirements

## REMOVED Requirements
