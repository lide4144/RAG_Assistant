## ADDED Requirements

### 需求:系统必须提供 LiteLLM 统一调用适配层
系统必须在 Python 进程内通过统一适配层完成 LLM 非流式与流式调用，调用方必须继续使用既有 `llm_client` 接口，禁止在业务模块直接耦合具体供应商 SDK。

#### 场景:rewrite 调用保持接口兼容
- **当** rewrite 模块发起 LLM 调用
- **那么** 系统必须返回与历史 `LLMCallResult` 契约兼容的字段结构

### 需求:系统必须支持 OpenAI-compatible API 基址配置
系统必须支持通过配置声明 `api_base` 与 `api_key` 来源来访问 OpenAI-compatible 模型端点，禁止将 endpoint 固定写死在代码中。

#### 场景:切换供应商端点无需改业务代码
- **当** 变更模型供应商的 API 基址
- **那么** 系统必须仅通过配置变更完成切换且无需修改 rewrite/qa 业务代码

## MODIFIED Requirements
<!-- 无 -->

## REMOVED Requirements
<!-- 无 -->
