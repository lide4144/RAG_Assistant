## 1. 规则删除与边界收缩

- [x] 1.1 盘点 `app/sufficiency.py` 中所有静态问题类型词表、关键要素槽位映射、token overlap / trigram 近似语义规则
- [x] 1.2 删除不再保留的语义规则路径，包括基于 `QUESTION_TYPE_*`、`KEY_ELEMENT_*`、`_topic_match_score`、`_semantic_similarity_score_fallback` 直接裁决不足的逻辑
- [x] 1.3 盘点并删除 `app/qa.py` 中仅为 `sufficiency gate` 服务的重复规则常量或同构判断，重点包括 `KEY_ELEMENT_*`、`QUESTION_TYPE_*` 及其派生逻辑，防止双份维护
- [x] 1.4 确认 `app/qa.py` 中控制意图、planner 路由或非 sufficiency 职责的规则不被误删，明确本次清理边界

## 2. 新的证据检验结构

- [x] 2.1 引入 `semantic evidence judge（语义证据判别）` 模块或等价抽象，输出结构化 `coverage_summary`、`missing_aspects`、`decision_hint`
- [x] 2.2 将 `sufficiency gate` 改为消费 `semantic judge` 结果，而不是维护静态问题类型/槽位规则
- [x] 2.3 保留并收敛 `hard validator（硬校验）`，仅负责最小证据数量、内容类型噪声、引用/证据存在性和明显越界阻断
- [x] 2.4 明确 judge 不可用或不确定时的受控降级语义，禁止重新回退到旧规则词表裁决

## 3. 交互契约与输出重构

- [x] 3.1 将 `sufficiency` 输出中的 `missing_key_elements` 迁移为更通用的 `missing_aspects` / `coverage_summary`
- [x] 3.2 更新 planner/QA 对 `sufficiency` 结果的消费方式，确保上层不再依赖旧槽位名
- [x] 3.3 为 trace 和调试输出补充 `judge_source`、`validator_source`、`coverage_summary` 等可审计字段

## 4. 测试与清理

- [x] 4.1 重写 `sufficiency` 相关测试，使验收口径从“规则命中”改为“结构化证据判别 + 硬校验”
- [x] 4.2 增加回归测试，验证开放式总结、隐式数值问题、跨语言问法和长尾表达不再被静态槽位规则误伤
- [x] 4.3 增加测试，验证完全无证据、仅噪声证据、引用越界等场景仍会被硬校验稳定阻断
- [x] 4.4 删除或标记不再适用的旧规则回归用例、文档与注释，避免后来者继续往 `sufficiency` 里追加规则
