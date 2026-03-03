## 1. Gate 接入与数据结构

- [x] 1.1 在回答编排入口新增 `run_sufficiency_gate(question, top_n_evidence)` 调用点
- [x] 1.2 扩展回答输出 schema，新增 `decision`、`reason`、`clarify_questions`（可选）
- [x] 1.3 增加配置开关与阈值项（相关性门限、关键槽位覆盖门限）并提供默认值

## 2. Sufficiency Gate 核心逻辑

- [x] 2.1 实现主题匹配不足检测（相关性低）并产出可解释 `reason`
- [x] 2.2 实现关键要素缺失检测（数值/方法/限定条件槽位）并产出缺失类型
- [x] 2.3 实现决策选择器，保证仅输出 `answer/refuse/clarify` 三值之一
- [x] 2.4 实现 `clarify` 问题生成器，确保仅返回 1~2 个问题且直指缺失信息

## 3. 输出分支与降级行为改造

- [x] 3.1 改造 orchestrator：`decision=answer` 才允许进入正常回答生成路径
- [x] 3.2 实现 `decision=refuse` 拒答模板分支并追加 `insufficient_evidence_for_answer`
- [x] 3.3 实现 `decision=clarify` 分支，禁止同时输出事实性最终答案
- [x] 3.4 将新分支行为与现有 `output-consistency-evidence-allocation` 校验对齐

## 4. 测试与验收

- [x] 4.1 增加单测：主题不匹配场景触发 `refuse` 或 `clarify`
- [x] 4.2 增加单测：关键要素缺失（数值/方法细节）触发 `refuse` 或 `clarify`
- [x] 4.3 增加单测：`clarify_questions` 数量约束为 1~2
- [x] 4.4 构造 10 个语料库外问题回归集并验证 10/10 不进入 `answer`
- [x] 4.5 增加集成测试，验证 Gate 决策可稳定驱动 answer/refuse/clarify 三分支

## 5. 观测与文档

- [x] 5.1 为 Gate 输出补充诊断日志（判定特征、触发规则、最终决策）
- [x] 5.2 更新开发文档，说明 M8 决策语义、阈值调参与验收脚本运行方式
