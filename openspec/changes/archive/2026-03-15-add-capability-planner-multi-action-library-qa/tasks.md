## 1. Unified Resolver + Planner

- [x] 1.1 为统一 planner 定义结构化输入输出契约与配置开关，包括 `is_new_topic`、`standalone_query`、`primary_capability`、`strictness`、`action_plan` 与 `planner_confidence`
- [x] 1.2 在现有 QA 入口前接入统一 planner 调用、JSON 校验与失败回退逻辑
- [x] 1.3 将 planner 观测字段写入 run trace，并保持与现有 trace 消费方兼容

## 2. 顺序执行器与目录复用

- [x] 2.1 实现受限 `action_plan` 执行器，支持 `catalog_lookup`、`cross_doc_summary`、`fact_qa`、`control` 四类动作
- [x] 2.2 复用现有目录元数据源，提供聊天侧可调用的 `catalog_lookup` 能力与 `paper_set` 产物
- [x] 2.3 为执行器增加依赖校验、空结果短路与短路结果观测字段
- [x] 2.4 为目录结果增加硬上限、排序选择与 `matched_count/selected_count/truncated` 披露

## 3. 状态机与严格度分流

- [x] 3.1 在 `waiting_followup`/`need_clarify` 状态下接入换题检测，并在识别新话题时清除挂起澄清状态与主题澄清计数
- [x] 3.2 为请求执行链路引入 `strictness` 分流，区分 `catalog`、`summary`、`strict_fact`
- [x] 3.3 实现 strict fact 二次拦截，防止数值/作者/实验设置类问题误流入宽松 summary 路径
- [x] 3.4 收窄 `sufficiency_gate` 与 `evidence_policy_gate` 的适用范围，仅在 strict fact 路径保持最严格门控

## 4. Summary 路径与降级策略

- [x] 4.1 为 `cross_doc_summary` 定义最小覆盖与降级规则，支持 `preliminary summary` 或缩小范围提示
- [x] 4.2 支持 `catalog_lookup -> cross_doc_summary` 的复合查询结果拼装与表格化输出参数传递
- [x] 4.3 在 summary 路径中补充范围来源、使用论文集合与截断披露结果

## 5. 测试与回归验证

- [x] 5.1 增加统一 planner 的单元测试，覆盖新话题、单步路由、复合查询拆解与 planner 失败回退
- [x] 5.2 增加执行器测试，覆盖空结果短路、结果集截断与步骤依赖校验
- [x] 5.3 增加 strict fact 逃逸拦截测试，确保“对比准确率具体数值”等问题被升级到严格路径
- [x] 5.4 增加多轮状态回归测试，确保 `waiting_followup` 下的新问题不会再机械拼接旧澄清问题
