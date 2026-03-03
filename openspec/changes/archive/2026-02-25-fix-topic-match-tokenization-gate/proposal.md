## 为什么

当前 Sufficiency Gate 在处理中英无空格混写问题（如 `Transformer是什么`）时，可能把问题分词为单个复合 token，导致 `topic_match_score` 被错误计算为 0，并触发 `topic_mismatch` 误拒答。该问题已在真实运行日志中复现，会直接降低系统可用性并误导调试定位。

## 变更内容

- 修正主题匹配分词策略，使中英混写、符号边界与常见中文问句后缀在匹配中可被稳定切分。
- 调整 Sufficiency Gate 的主题匹配判定策略，降低因单一路径分词异常导致的误拒风险。
- 增强拒答来源可观测性，明确区分由 Sufficiency Gate 与 Evidence Policy Gate 触发的拒答路径，避免诊断混淆。

## 功能 (Capabilities)

### 新增功能
- `topic-match-tokenization`: 提供面向主题匹配的鲁棒分词与边界切分能力，覆盖中英混写问句场景。

### 修改功能
- `sufficiency-gate`: 调整 topic match 计算与判定稳健性，避免相关证据被误判为主题不匹配。
- `output-consistency-evidence-allocation`: 增加拒答来源可追踪字段与文案一致性要求，避免将非 Sufficiency Gate 拒答误标为 Sufficiency Gate。

## 影响

- 代码：`app/qa.py` 中主题匹配分词、Sufficiency Gate 判定与拒答文案/trace 输出路径。
- 测试：补充分词边界与主题匹配回归用例；补充拒答来源一致性用例。
- 运行行为：降低 `topic_mismatch` 误拒答率，同时保持库外问题拒答能力。
