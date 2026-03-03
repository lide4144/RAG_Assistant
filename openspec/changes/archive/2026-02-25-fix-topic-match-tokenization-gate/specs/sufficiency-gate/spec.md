## MODIFIED Requirements

### 需求:主题不匹配必须触发不足
当 `top_n evidence` 与问题主题相关性低于门限时，系统必须判定为证据不足，且禁止直接进入 `answer` 决策。系统必须基于 `standalone_query` 与 `query_used(calibrated_query)` 两条路径计算主题匹配分数并输出可审计结果；最终判定必须采用稳健聚合分数，防止单一路径分词异常导致误拒。

#### 场景:相关性低触发拒答或澄清
- **当** 证据主题与问题主题不匹配且稳健聚合后的相关性低于门限
- **那么** 系统必须输出 `refuse` 或 `clarify`，并在 `reason` 中说明“主题不匹配/相关性不足”

#### 场景:中英混写问题不得因分词异常误拒
- **当** 问题为 `Transformer是什么` 且证据明确包含 Transformer 定义性片段
- **那么** 系统不得仅因 `topic_match_score` 分词异常触发 `topic_mismatch` 拒答

#### 场景:双路径分数必须可追踪
- **当** Sufficiency Gate 完成一次主题匹配判定
- **那么** 运行产物必须能追踪 `standalone_query` 路径分数、`query_used` 路径分数与最终聚合分数

## ADDED Requirements

## REMOVED Requirements
