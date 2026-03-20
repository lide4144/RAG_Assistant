## 1. 交互裁判权收口

- [x] 1.1 盘点并标记所有当前会在 planner 决策之后改写 `clarify / partial_answer / refuse（澄清 / 部分回答 / 拒答）` 的代码路径
- [x] 1.2 定义统一的 `final interaction decision contract（最终交互决策契约）`，明确 `planner / policy（规划器 / 策略层）` 输出的唯一最终用户姿态字段
- [x] 1.3 将 `planner runtime（规划运行时）` 改造为写出 `final_interaction_authority（最终交互裁判）` 与 `interaction_decision_source（交互决策来源）`
- [x] 1.4 移除或封禁 `qa.py` 中在 planner 决策之后尾部重写最终用户姿态的逻辑

## 2. 底层约束信封重构

- [x] 2.1 定义 `constraints envelope（约束信封）` 的最小结构与稳定字段，并为 kernel / tool / guardrail 路径提供统一构造入口
- [x] 2.2 将 `sufficiency gate（充分性门控）` 的输出改造为结构化约束对象，而不是最终姿态裁判
- [x] 2.3 将 `evidence gate（证据门）` 与引用合法性检查改造为返回 `guardrail block（护栏阻断）` 或约束摘要，而不是直接生成用户拒答
- [x] 2.4 让 planner / policy（规划器 / 策略层）消费 `constraints envelope（约束信封）` 并统一决定 `clarify / partial_answer / refuse（澄清 / 部分回答 / 拒答）`

## 3. 多轮澄清状态收口

- [x] 3.1 将 `pending clarify（挂起澄清）`、`same topic / new topic（同话题 / 新话题）` 与澄清计数统一收口到 `planner state（规划器状态）`
- [x] 3.2 移除或降权旧 QA / rewrite（问答链 / 改写）里依赖局部规则拼接澄清补充的路径
- [x] 3.3 验证“上一轮澄清、下一轮补标题/线索”能够恢复原问题链路，而不是重新走目录列举或再次机械澄清

## 4. 控制意图与主链隔离

- [x] 4.1 调整 `control-intent-routing（控制意图路由）`，确保控制意图由 `planner / policy（规划器 / 策略层）` 在检索前识别
- [x] 4.2 禁止“用中文回答我”“换成表格展示”等控制意图误入证据型 QA 主链
- [x] 4.3 为控制意图与主能力共存场景补齐结构化参数透传与回归验证

## 5. Trace 与回归验证

- [x] 5.1 在 `run trace（运行追踪）` 中补齐 `final_interaction_authority（最终交互裁判）`、`final_user_visible_posture（最终用户可见姿态）`、`kernel_constraint_summary（内核约束摘要）` 与 `posture_override_forbidden（被禁止的尾部改写）`
- [x] 5.2 为明确单篇论文元数据问题补充回归用例，验证命中证据后不再被错误要求“主体限定”
- [x] 5.3 为控制意图场景补充回归用例，验证其不再触发基于证据的拒答
- [x] 5.4 为多轮澄清闭环补充回归用例，验证补充线索后能回到原问题而不是重新漂移
- [x] 5.5 为被禁止的 `legacy qa tail override（旧问答尾部改写）` 增加检测与测试，确保一旦出现即被标记为错误状态
