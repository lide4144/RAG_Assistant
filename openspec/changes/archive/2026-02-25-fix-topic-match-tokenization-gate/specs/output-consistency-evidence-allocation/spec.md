## MODIFIED Requirements

### 需求:证据不足降级
当证据总量不足、证据质量不足、关键结论追溯校验失败、Sufficiency Gate 判定为 `refuse` 或 `clarify`、或 Gate 检测到主题不匹配/关键要素缺失时，系统必须阻断默认回答分支并进入受控降级路径。系统必须输出 `decision` 与 `reason`；当 `decision=clarify` 时必须输出 1~2 个 `clarify_questions`；当 `decision=refuse` 时必须输出拒答模板并追加 `insufficient_evidence_for_answer`，禁止自由发挥与编造。系统必须额外输出拒答来源字段（如 `final_refuse_source`），并确保拒答文案与来源一致。

#### 场景:Gate 不通过触发受控降级
- **当** evidence 总数小于阈值、evidence 为空、主题不匹配、关键要素缺失或 Gate 判定不通过
- **那么** 系统必须阻断默认回答生成，并输出 `refuse` 或 `clarify` 决策及可解释 `reason`

#### 场景:clarify 决策输出澄清问题
- **当** Sufficiency Gate 判定为 `clarify`
- **那么** 系统必须输出 1~2 个直接指向缺失信息的澄清问题，且不得同时输出事实性最终答案

#### 场景:refuse 决策禁止编造
- **当** Sufficiency Gate 判定为 `refuse`
- **那么** 系统必须输出拒答模板并记录 `insufficient_evidence_for_answer`，且不得输出未被 evidence 支撑的结论

#### 场景:拒答来源与文案一致
- **当** 最终拒答由 Evidence Policy Gate 触发而非 Sufficiency Gate
- **那么** 输出文案与 trace 必须标识对应来源，禁止统一宣称“已触发 Sufficiency Gate”

## ADDED Requirements

## REMOVED Requirements
