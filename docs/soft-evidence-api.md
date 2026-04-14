# Soft Evidence Handling API 文档

本文档描述了软性证据不足处理功能新增的 API 字段和行为变更。

## 概述

当系统检索到的证据有限（仅 1 条）时，现在会进入"低置信度模式"，允许结合模型知识生成回答，同时通过明确的来源标注帮助用户理解回答的可信度。

## 证据阈值变更

- **旧阈值**：最少需要 2 条证据
- **新阈值**：最少需要 1 条证据

## Sufficiency Gate 新增字段

### `answer_mode`

**类型**: `string`

**可选值**:
- `"evidence_only"` - 回答仅基于知识库证据（2+ 条证据）
- `"low_confidence_with_model_knowledge"` - 回答结合模型知识补充（仅 1 条证据）

**说明**: 标识当前回答的证据来源模式。

### `allows_model_knowledge`

**类型**: `boolean`

**说明**: 是否允许使用模型训练知识补充回答。当 `answer_mode` 为 `"low_confidence_with_model_knowledge"` 时为 `true`。

### `confidence_level`

**类型**: `string`

**可选值**:
- `"low"` - 1 条证据
- `"medium"` - 2 条证据
- `"high"` - 3+ 条证据

**说明**: 回答的置信度级别，基于证据数量。

### `evidence_count`

**类型**: `integer`

**说明**: 实际检索到的证据数量。

## 回答格式变更

### 内联来源标注

当进入低置信度模式时，回答中的每句话末尾会标注来源：

- `[📄 chunk_id]` - 内容来自知识库证据
- `[🤖 模型推测]` - 内容来自模型训练知识

**示例**:
```
深度学习在NLP领域取得了突破性进展[📄 chunk_001]。
Transformer架构可能是未来的主流[🤖 模型推测]。
BERT模型于2018年提出[📄 chunk_002]。
```

## Session State 用户偏好

### `user_honesty_preferences`

存储在 session state 中，用于记录用户对低置信度提示的偏好。

**字段**:
- `hide_low_confidence_warnings` (boolean) - 是否隐藏低置信度警告
- `acknowledged_at` (string, ISO 8601) - 上次确认时间
- `acknowledgment_count` (integer) - 点击"继续查看"的次数

**自动重置**: 偏好设置在 24 小时后自动重置。

## API 响应示例

### 1 条证据（低置信度模式）

```json
{
  "decision": "answer",
  "answer_mode": "low_confidence_with_model_knowledge",
  "allows_model_knowledge": true,
  "confidence_level": "low",
  "evidence_count": 1,
  "reason": "证据有限（仅1条），将结合模型知识给出最佳回答，请谨慎参考。",
  "reason_code": "insufficient_evidence_allow_model_knowledge",
  "severity": "warning",
  "triggered_rules": ["insufficient_evidence_allow_model_knowledge"],
  "output_warnings": ["insufficient_evidence_allow_model_knowledge"],
  "constraints_envelope": {
    "constraint_type": "partial_answer",
    "reason_code": "insufficient_evidence_allow_model_knowledge",
    "severity": "warning",
    "allows_partial_answer": true
  }
}
```

### 2 条证据（正常模式）

```json
{
  "decision": "answer",
  "answer_mode": "evidence_only",
  "allows_model_knowledge": false,
  "confidence_level": "medium",
  "evidence_count": 2,
  "reason": "证据充分，可进入回答。",
  "reason_code": "ready_to_answer",
  "severity": "info"
}
```

### 0 条证据（拒绝）

```json
{
  "decision": "refuse",
  "reason": "证据数量或质量不足，无法可靠回答。",
  "reason_code": "insufficient_evidence_count_or_quality",
  "severity": "high"
}
```

## 向后兼容性

所有新增字段都是**可选的**，现有代码可以安全地忽略它们：

- 旧版前端无需修改即可正常工作
- 原有字段的值和行为保持不变
- 新字段只在特定条件下出现

## 特殊场景处理

### 开放式总结 (open_summary_intent)

当用户请求开放式总结（如"总结这些论文"）时，即使只有 1 条证据，系统仍会要求澄清：

```json
{
  "decision": "clarify",
  "clarify_questions": ["你最关心哪一类主题（方法、实验结果、应用场景）？"]
}
```

### 仅噪声内容

如果唯一的证据来自 front_matter 或 reference，仍会被视为证据不足。

## 配置项

当前实现**不需要**新增配置项。所有行为通过代码逻辑控制。

## 注意事项

1. **模型标注准确性**: LLM 可能无法 100% 准确区分证据内容和模型知识，建议结合引用验证。

2. **成本考量**: 低置信度模式会调用 LLM 生成回答，已投入的计算成本不会浪费。

3. **用户体验**: 首次使用时会显示提示，用户可选择"不再提示"，24 小时后自动重置。

## 相关测试

- `tests/test_soft_evidence_threshold.py` - 证据阈值逻辑测试
- `tests/test_user_honesty_preferences.py` - 用户偏好存储测试
- `tests/test_soft_evidence_integration.py` - 集成测试
