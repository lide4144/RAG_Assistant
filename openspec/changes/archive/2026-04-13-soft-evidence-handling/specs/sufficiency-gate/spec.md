## 修改需求

### 需求:证据阈值放宽
Sufficiency Gate 的最小证据阈值必须从 2 条修改为 1 条。当证据数量为 1 条时，不得再判定为"证据不足"而直接拒绝。

**修改内容**:
- FROM: `min_evidence = 2`
- TO: `min_evidence = 1`

#### 场景:1条证据时允许回答
- **当** `_is_insufficient_evidence` 函数被调用
- **并且** 检索到 1 条有效证据
- **那么** 函数必须返回 `False`（证据充足）
- **并且** 系统可以继续进入回答流程

#### 场景:0条证据时仍然不足
- **当** `_is_insufficient_evidence` 函数被调用
- **并且** 检索到 0 条证据
- **那么** 函数必须返回 `True`（证据不足）
- **并且** 系统必须进入拒绝流程

### 需求:低置信度回答模式
当 Sufficiency Gate 判定证据不足但至少存在 1 条证据时，系统必须返回 `decision: "answer"` 并设置 `answer_mode: "low_confidence_with_model_knowledge"`，而非返回 `decision: "refuse"`。

**修改内容**:
- FROM: 证据不足时返回 `decision: "refuse"` 或 `"clarify"`
- TO: 证据不足但有1条证据时返回 `decision: "answer"`，`answer_mode: "low_confidence_with_model_knowledge"`

#### 场景:证据不足但有1条证据时的新决策
- **当** Sufficiency Gate 判定证据不足（`_is_insufficient_evidence` 为 True）
- **并且** 实际证据数量为 1 条
- **那么** `report["decision"]` 必须设置为 `"answer"`
- **并且** `report["answer_mode"]` 必须设置为 `"low_confidence_with_model_knowledge"`
- **并且** `report["allows_model_knowledge"]` 必须设置为 `true`
- **并且** `report["reason"]` 必须说明"证据有限，将结合模型知识"

#### 场景:新字段的完整结构
- **当** 系统返回低置信度回答决策
- **那么** 返回值必须包含新增字段：
  - `answer_mode`: "low_confidence_with_model_knowledge"
  - `allows_model_knowledge`: true
  - `confidence_level`: "low"
