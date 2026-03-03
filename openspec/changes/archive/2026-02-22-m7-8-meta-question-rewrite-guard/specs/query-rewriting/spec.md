## 新增需求

### 需求:元问题状态感知转写护栏
系统必须在 rewrite 阶段识别元问题追问（如“为什么没证据”“你没回答全”“再找找具体组成”及同义表达），并在命中时将状态追问转写为面向事实补证的可检索查询；禁止将抱怨词、系统状态词直接作为检索目标。

#### 场景:命中元问题后执行事实转写
- **当** 当前用户输入命中元问题模式
- **那么** 系统必须设置 `rewrite_meta_detected=true`，并输出基于历史实体的事实检索 `standalone_query`

#### 场景:上一轮证据不足时优先补证据
- **当** `last_turn_warnings` 包含 `insufficient_evidence_for_answer` 且当前命中元问题
- **那么** 系统必须优先将查询转写为补证据目标（如架构细节、机制解释、实验设置、指标定义）并设置 `rewrite_guard_applied=true`

#### 场景:禁止机械拼接历史问句
- **当** 系统生成 `standalone_query`
- **那么** 输出必须为单一可检索短语，禁止“上一轮问题 + 当前问题”机械拼接，且不得包含重复问句片段

### 需求:实体保真与最小增补
在元问题护栏转写中，系统必须保留历史核心实体（论文名、方法名、指标名）；仅允许补充最小必要限定词，不得引入无关新任务。

#### 场景:实体保真
- **当** `entities_from_history` 中存在核心实体
- **那么** `standalone_query` 必须包含至少一个核心实体，并保持原问题任务边界

#### 场景:限制无关扩写
- **当** 系统执行护栏转写
- **那么** 不得新增与当前实体无关的任务目标或跨域问题

### 需求:元问题护栏可观测与失败降级
系统必须输出 `rewrite_meta_detected`、`rewrite_guard_applied`、`rewrite_guard_strategy`；当 LLM rewrite 不可用或输出异常时必须回退规则改写并记录 `rewrite_notes`。

#### 场景:LLM 输出异常触发回退
- **当** LLM rewrite 返回空串、污染串或越界任务
- **那么** 系统必须回退规则转写，`rewrite_guard_applied=true`，并在 `rewrite_notes` 记录回退原因

#### 场景:输出字段可追踪
- **当** 任意一次 rewrite 完成
- **那么** 结果中必须包含 `rewrite_meta_detected`、`rewrite_guard_applied`、`rewrite_guard_strategy`，并可序列化写入 trace

## 修改需求

### 需求:Query Rewriting 基础产出
系统必须将输入问题 `Q` 改写为检索查询 `Q'`，并同时输出 `keywords/entities` 结构供检索增强使用。多轮模式下，系统必须先生成 `standalone_query`，再执行规则/LLM 改写；`Q'` 必须以 `standalone_query` 为输入基础。若命中元问题护栏，`standalone_query` 必须优先表达可证据化的事实检索意图，而非系统状态追问。

#### 场景:多轮输入先独立化再改写
- **当** 请求携带 `session_id` 且存在历史轮次
- **那么** 系统必须先产出 `standalone_query`，并基于该查询进入 rewrite 流程

#### 场景:元问题场景保持检索导向
- **当** 当前问题为状态追问且存在可继承实体
- **那么** `standalone_query` 必须转写为实体相关事实查询，并保持可检索短语形式

## 移除需求

- 无
