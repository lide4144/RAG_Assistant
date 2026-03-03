## MODIFIED Requirements

### 需求:系统必须持久化 LLM 路由配置
系统必须提供持久化结构保存管理员选择的路由配置，并支持读取最新生效配置。持久化配置必须覆盖 `answer`、`embedding`、`rerank` 三个 stage，每个 stage 至少包含 `api_base`、`api_key`、`model` 与 `provider`。系统必须支持向后兼容旧格式配置并映射到新结构。

#### 场景:保存后读取多 stage 配置
- **当** 管理员保存 answer、embedding、rerank 的配置
- **那么** 系统必须在后续读取时返回三个 stage 的最新保存值

## ADDED Requirements

### 需求:系统必须消除单一环境变量硬依赖
系统必须通过 stage 配置的 `api_key_env` 解析密钥，禁止把 `SILICONFLOW_API_KEY` 作为唯一默认依赖。若某 stage 未配置可用密钥，系统必须仅影响该 stage 并返回可观测告警，禁止拖垮其他 stage。

#### 场景:embedding 缺失 key 不影响 answer
- **当** embedding 未配置可用 API key 且 answer 配置完整
- **那么** 系统必须保持 answer 路由可用，并将 embedding 标记为不可用或降级

