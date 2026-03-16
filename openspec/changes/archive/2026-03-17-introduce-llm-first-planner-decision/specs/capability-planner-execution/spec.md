## 新增需求

### 需求:系统必须支持 llm-first planner source 与受控回退
系统必须让 planner runtime 支持 `rule_only`、`shadow_compare` 与 `llm_primary_with_rule_fallback` 三种 planner source 模式，并在 `llm_primary_with_rule_fallback` 模式下优先执行通过 validation 的 LLM decision；禁止在未声明 planner source 模式的情况下隐式切换顶层决策来源。

#### 场景:LLM 主决策失败后回退规则 planner
- **当** 系统运行在 `llm_primary_with_rule_fallback` 模式且 LLM decision 被 validation gate 拒绝
- **那么** planner runtime 必须回退到 rule planner，而不是直接中断请求

#### 场景:rule_only 模式保持现有行为
- **当** 系统运行在 `rule_only` 模式
- **那么** planner runtime 必须继续仅使用 rule planner 产出 decision，并保持现有兼容链路可用

### 需求:系统必须将 planner 决策与 QA 交互姿态解耦
系统必须将“是否澄清、是否给部分回答、是否拒答”的顶层交互姿态定义为 planner / policy 决策结果，而 deterministic kernel 仅负责输出证据、依赖或 citation 约束信号；禁止继续由 `qa.py` 在 planner 决策之后独立重写本轮最终交互姿态。

#### 场景:kernel 输出约束信号但不独占最终姿态
- **当** deterministic kernel 判定当前请求证据不足或前置条件不满足
- **那么** kernel 必须输出约束信号供 planner / policy 消费，而不是绕过顶层 planner 直接决定最终用户姿态

#### 场景:planner 成为用户交互姿态真相源
- **当** 本轮请求最终以 `clarify`、`partial answer` 或 `refuse` 收束
- **那么** 运行 trace 必须能表明该姿态来自 planner / policy 决策，而不是无法区分地混入底层 QA 尾部规则
