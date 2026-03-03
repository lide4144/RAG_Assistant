## 为什么

当前问答链路在证据不足时仍可能输出推断性答案，存在“语料库外问题被编造回答”的风险。M8 需要在生成前增加证据充分性判断，让系统在证据不够时明确拒答或发起澄清，提升可信度与可控性。

## 变更内容

- 在回答阶段前新增 Sufficiency Gate，对 `top_n evidence` 与问题 `Q` 进行充分性评估。
- 输出统一决策结构：`decision`（`answer`/`refuse`/`clarify`）与 `reason`。
- 当决策为 `clarify` 时，额外输出 1~2 个澄清问题。
- 新增两类显式不足触发规则：
  - 证据主题与问题不匹配（相关性低）。
  - 证据缺失关键要素（如数值、方法细节等）。
- 增加评测与验收用例：至少 10 个语料库外问题需稳定拒答，不得编造。

## 功能 (Capabilities)

### 新增功能
- `sufficiency-gate`: 在最终作答前执行证据充分性判断，并产出 answer/refuse/clarify 决策与理由。

### 修改功能
- `output-consistency-evidence-allocation`: 将 Sufficiency Gate 决策接入最终输出路径，确保 refusal/clarify 走独立输出分支而非默认回答分支。

## 影响

- 受影响代码：检索后处理、提示词组装与最终响应编排模块。
- 受影响数据结构：回答对象需包含 `decision`、`reason`、`clarify_questions`（可选）。
- 受影响测试：新增 insufficiency 场景单测/集成测试与语料库外问题集回归测试。
