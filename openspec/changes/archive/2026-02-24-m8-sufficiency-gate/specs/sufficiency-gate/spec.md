## ADDED Requirements

### 需求:Sufficiency Gate 决策输出
系统必须在最终回答前基于 `question` 与 `top_n evidence` 产出单一决策对象，字段至少包含 `decision` 与 `reason`；其中 `decision` 必须为 `answer`、`refuse`、`clarify` 三者之一。 当 `decision=clarify` 时，系统必须额外输出 `clarify_questions`，且数量必须为 1~2 个。

#### 场景:输出结构合法
- **当** 系统收到一次问答请求并完成证据聚合
- **那么** 系统必须返回包含 `decision` 与 `reason` 的决策对象，且 `decision` 取值仅限 `answer/refuse/clarify`

#### 场景:clarify 输出问题数量受控
- **当** Sufficiency Gate 判定为 `clarify`
- **那么** 输出必须包含 `clarify_questions`，且问题数量必须为 1 或 2

### 需求:主题不匹配必须触发不足
当 `top_n evidence` 与问题主题相关性低于门限时，系统必须判定为证据不足，且禁止直接进入 `answer` 决策。

#### 场景:相关性低触发拒答或澄清
- **当** 证据主题与问题主题不匹配且相关性低于门限
- **那么** 系统必须输出 `refuse` 或 `clarify`，并在 `reason` 中说明“主题不匹配/相关性不足”

### 需求:关键要素缺失必须触发不足
当问题要求关键要素（如数值、方法步骤、实验条件、时间/主体限定）而证据未覆盖时，系统必须判定为证据不足，且禁止直接进入 `answer` 决策。

#### 场景:缺失数值或方法细节触发不足
- **当** 问题明确要求数值或方法细节，且 `top_n evidence` 未提供对应要素
- **那么** 系统必须输出 `refuse` 或 `clarify`，并在 `reason` 中指明缺失的关键要素类型

### 需求:语料库外问题默认拒答
对人工构造的语料库外问题集，系统必须优先拒答而非编造；在标准验收集中至少 10 个语料库外问题均不得进入 `answer`。

#### 场景:语料库外 10 题拒答通过
- **当** 执行语料库外问题回归测试并输入 10 个构造问题
- **那么** 10/10 样例的 `decision` 必须为 `refuse` 或 `clarify`，且不得输出编造性事实答案
