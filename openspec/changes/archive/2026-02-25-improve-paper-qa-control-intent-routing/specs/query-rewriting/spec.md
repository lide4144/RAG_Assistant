## ADDED Requirements

### 需求:控制意图不得作为独立检索查询改写
当输入被判定为 `style_control`、`format_control` 或 `continuation_control` 时，系统必须禁止将控制语句本身改写为检索查询；系统必须基于会话锚定主题生成 `query_used` 或直接复用锚定查询。

#### 场景:用中文回答不触发控制词检索
- **当** 当前输入为“用中文回答我”且存在可用主题锚点
- **那么** 系统输出的 `rewrite_query` 必须为锚定主题查询，不得为“用中文回答我”或其同义控制词

## MODIFIED Requirements

### 需求:Query Rewriting 基础产出
系统必须将输入问题 `Q` 改写为检索查询 `Q'`，并同时输出 `keywords/entities` 结构供检索增强使用。多轮模式下，系统必须先生成 `standalone_query`，再执行规则/LLM 改写；`Q'` 必须以 `standalone_query` 为输入基础。若命中元问题护栏，`standalone_query` 必须优先表达可证据化的事实检索意图，而非系统状态追问。若输入被 Intent Router 识别为控制意图，系统必须优先采用会话锚定主题进行改写或复用，禁止将控制词作为主题词进入检索。

#### 场景:多轮输入先独立化再改写
- **当** 请求携带 `session_id` 且存在历史轮次
- **那么** 系统必须先产出 `standalone_query`，并基于该查询进入 rewrite 流程

#### 场景:元问题场景保持检索导向
- **当** 当前问题为状态追问且存在可继承实体
- **那么** `standalone_query` 必须转写为实体相关事实查询，并保持可检索短语形式

#### 场景:控制意图场景优先锚定主题
- **当** 当前输入被判定为 `style_control` 或 `format_control`
- **那么** 系统必须使用 `anchor_query` 作为改写输入基础，禁止将控制词直接作为 `Q'`

