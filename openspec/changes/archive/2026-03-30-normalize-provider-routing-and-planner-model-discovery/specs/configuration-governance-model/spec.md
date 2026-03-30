## 新增需求

无

## 修改需求

### 需求:系统必须定义统一的来源优先级语义
系统必须为不同 owner 字段提供统一的来源优先级解释。`static` 字段必须以静态配置为基线并回退到安全默认值；`runtime` 字段必须声明是否允许环境变量覆盖，并在允许时明确 `env`、runtime 持久化与默认值之间的优先级；`env_only` 字段必须由环境变量控制，禁止伪装为前端或静态可编辑字段。对于使用外部模型服务的 runtime LLM 配置，系统还必须定义 provider 规范化语义：聊天、规划和其他 OpenAI-compatible 调用链路必须以协议语义持久化 provider，而不是直接以服务商品牌名充当通用 provider；仅当某阶段依赖品牌专用原生接口时，系统才可保留该原生 provider 名称。

#### 场景:查询字段最终值来源
- **当** 管理员或开发者查看某个配置字段的最终生效值
- **那么** 系统必须能够用一致语义解释该值来自 `default`、`runtime`、`env` 或安全默认回退

#### 场景:保存 OpenAI-compatible 运行时配置
- **当** 管理员保存使用 SiliconFlow 等 OpenAI-compatible 服务的聊天或规划类运行时配置
- **那么** 系统必须按 OpenAI-compatible 语义规范化 provider，而不是把服务商品牌名作为通用 provider 原样持久化

#### 场景:保存原生专用运行时配置
- **当** 管理员保存依赖原生专用协议的 `embedding` 或 `rerank` 运行时配置
- **那么** 系统必须允许保留对应原生 provider 名称，而不得被强制规范化为 OpenAI-compatible provider

## 移除需求
