## ADDED Requirements

### 需求:系统必须在检索前执行控制意图路由
系统必须在问答入口对用户输入执行意图分类，分类结果至少包含 `retrieval_query`、`style_control`、`format_control`、`continuation_control`。当分类结果不是 `retrieval_query` 时，系统必须禁止将原始输入直接作为新检索查询。

#### 场景:语言切换输入被识别为控制意图
- **当** 用户输入“用中文回答我”或等价语言切换指令
- **那么** 系统必须将本轮 `intent_type` 判定为 `style_control`，且不得把该输入直接写入检索 query

#### 场景:普通事实问题保持检索路径
- **当** 用户输入“Transformer 有什么用”
- **那么** 系统必须将 `intent_type` 判定为 `retrieval_query`，并按常规改写与检索流程执行

### 需求:系统必须提供可配置的路由开关与回退
系统必须提供 `intent_router_enabled` 配置项。关闭时系统必须回退到现有默认流程并保证行为兼容；开启时必须在 trace 输出 `intent_type` 与路由来源信息。

#### 场景:路由开关关闭时兼容旧流程
- **当** `intent_router_enabled=false`
- **那么** 系统必须跳过意图路由并保持原有 query 改写与检索行为

