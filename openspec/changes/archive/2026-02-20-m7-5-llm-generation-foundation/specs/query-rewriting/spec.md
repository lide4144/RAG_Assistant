## ADDED Requirements

### 需求:clarify_scope 模式禁止 LLM 改写
当 `scope_mode=clarify_scope` 时，系统必须禁止调用 `llm_rewrite`，并直接沿用规则改写结果。

#### 场景:clarify_scope 直接跳过
- **当** Scope Policy 判定当前请求为 `clarify_scope`
- **那么** 系统必须不发起任何 LLM 改写请求，且 `rewrite_query` 必须等于 `rewrite_rule_query`

### 需求:LLM 改写失败原因可追踪
系统必须在 `strategy_hits` 中记录 LLM 改写结果状态，至少区分：调用成功、超时回退、限流回退、空响应回退与配置禁用。

#### 场景:失败路径记录命中
- **当** LLM 改写失败并触发回退
- **那么** `strategy_hits` 必须包含具体失败原因命中，且 `rewrite_llm_fallback` 必须为 `true`

## MODIFIED Requirements

### 需求:术语保留策略
系统必须在规则或 LLM 改写中保留原问题中的英文缩写、公式样式、关键数字指标与专有名词（如模型名、数据集名、指标名）；禁止丢失这些实体，也禁止引入与用户问题无关的新任务目标。

#### 场景:LLM 改写仍保留关键实体
- **当** 问题包含 `F1`、`BLEU`、`Top-1`、`AUC`、公式表达式或专有名词
- **那么** `rewrite_query` 必须保留这些术语或其等价字面表示，且不得生成与原问题无关的新目标

### 需求:可选 LLM 改写开关
系统必须提供可选 LLM 改写开关，默认关闭；当开关开启时必须优先尝试 LLM 改写，并在失败时回退规则改写；当开关关闭时必须仅使用规则改写。

#### 场景:LLM 开关关闭
- **当** `rewrite_use_llm=false`
- **那么** 系统必须只执行规则改写，`rewrite_llm_used=false`，`rewrite_llm_query` 为空

#### 场景:LLM 开关开启并成功
- **当** `rewrite_use_llm=true` 且 LLM 返回有效改写
- **那么** 系统必须设置 `rewrite_llm_used=true`，并以 `rewrite_llm_query` 作为最终 `rewrite_query`

#### 场景:LLM 开关开启但失败
- **当** `rewrite_use_llm=true` 且 LLM 调用超时、限流或返回空响应
- **那么** 系统必须设置 `rewrite_llm_fallback=true`，并将最终 `rewrite_query` 回退为 `rewrite_rule_query`

## REMOVED Requirements
