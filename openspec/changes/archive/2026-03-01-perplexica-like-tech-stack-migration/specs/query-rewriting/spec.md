## ADDED Requirements

### 需求:系统必须支持 rewrite 候选打分仲裁
系统必须同时产出 rule_query 与 llm_query 候选，并基于检索与重排质量信号选择最终 query；禁止仅凭固定阈值直接否决语义改写。

#### 场景:语义改写优于规则改写
- **当** llm_query 在候选检索质量上优于 rule_query
- **那么** 系统必须采用 llm_query 作为最终查询

### 需求:系统必须将硬规则降级为护栏
rewrite 规则必须用于约束与修补（如实体、数值、公式保真），不得作为默认阻断器覆盖语义改写主路径。

#### 场景:发现实体缺失时执行修补
- **当** llm_query 缺失关键实体但语义主体正确
- **那么** 系统必须执行最小修补并继续使用修补后查询

## MODIFIED Requirements
<!-- 无 -->

## REMOVED Requirements
<!-- 无 -->
