## MODIFIED Requirements

### 需求:系统必须持久化 LLM 路由配置
系统必须提供持久化结构保存管理员选择的路由配置，并支持读取最新生效配置。持久化配置必须覆盖 `answer`、`embedding`、`rerank` 三个 stage，每个 stage 至少包含 `api_base`、`api_key`、`model` 与 `provider`。系统必须支持向后兼容旧格式配置并映射到新结构。

#### 场景:保存后读取多 stage 配置
- **当** 管理员保存 answer、embedding、rerank 的配置
- **那么** 系统必须在后续读取时返回三个 stage 的最新保存值

## ADDED Requirements

### 需求:系统必须兼容旧单路配置载荷
系统在接收旧格式 `api_base/api_key/model` 载荷时必须继续可用，并将其映射到三路持久化结构，以避免历史客户端立即失效。

#### 场景:旧客户端调用保存接口
- **当** 客户端仅提交 `api_base/api_key/model`
- **那么** 系统必须成功保存并生成可被三路读取接口消费的配置结构
