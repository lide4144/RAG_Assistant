## 新增需求

无

## 修改需求

### 需求:统一 LLM 提供方与模型配置
系统必须支持独立的 rewrite/answer LLM 配置，并提供默认值：
- `rewrite_llm_provider=openai`
- `rewrite_llm_model=Pro/deepseek-ai/DeepSeek-V3.2`
- `answer_llm_provider=openai`
- `answer_llm_model=Pro/deepseek-ai/DeepSeek-V3.2`
并且必须支持 `llm_timeout_ms`、`llm_max_retries`、`llm_fallback_enabled`、`answer_stream_enabled`，以及回答阶段专用超时配置。对于使用 SiliconFlow 等 OpenAI-compatible 服务的聊天生成链路，系统必须通过 `api_base` 区分具体上游服务，而不得要求将服务商品牌名直接写入通用 provider 字段。

#### 场景:默认配置可加载
- **当** 用户未覆盖 LLM 相关配置
- **那么** 系统必须加载默认 provider/model，保留全局超时重试配置，并将回答流式开关置为安全默认值

#### 场景:使用 SiliconFlow 作为 OpenAI-compatible 上游
- **当** 系统将 SiliconFlow 用于 `answer` 或 `rewrite` 的聊天生成链路
- **那么** 系统必须允许通过 `provider=openai` 配合 SiliconFlow 的 `api_base` 完成调用，而不得要求使用 `provider=siliconflow`

### 需求:统一 LLM 鉴权与降级前置检查
系统必须通过运行时解析后的最终 API Key 进行鉴权；当开关开启但缺少鉴权信息时，系统必须记录降级原因并继续主流程，禁止抛出中断性错误。系统不得要求聊天生成链路仅依赖单一品牌命名的环境变量作为唯一鉴权入口。

#### 场景:缺少 API Key 自动降级
- **当** `rewrite_use_llm=true` 或 `answer_use_llm=true` 且最终解析后的 API Key 为空
- **那么** 系统必须跳过 LLM 调用并进入规则/模板路径，且运行日志必须包含可追踪降级原因

#### 场景:存在运行时持久化 Key
- **当** 运行时持久化配置已提供 `answer` 或 `rewrite` 的 API Key
- **那么** 系统必须使用该最终解析值完成鉴权，而不得因为缺少旧品牌命名环境变量而误判为不可用

## 移除需求
