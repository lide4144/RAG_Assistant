## 1. Registry 与共享契约

- [x] 1.1 在 Python kernel 中定义共享的 tool registry 数据结构，覆盖 `tool_name`、`capability_family`、`version`、`planner_visible`、`input_schema`、`result_schema`、`failure_types`、`streaming_mode`、`evidence_policy`、`produces` 与 `depends_on`
- [x] 1.2 定义统一的 tool `call envelope`、`result envelope` 与 `failure envelope` schema，并为 runtime 提供校验入口
- [x] 1.3 为首批本地能力建立注册表项：`catalog_lookup`、`fact_qa`、`cross_doc_summary`、`control`、`paper_assistant`
- [x] 1.4 为 `title_term_localization` 和后续研究辅助组合 tool 预留稳定注册入口与 evidence/streaming 元数据

## 2. Planner Runtime 接入

- [x] 2.1 在 planner runtime 执行阶段接入 registry 解析，禁止未经注册校验的 action 直接映射到内部函数
- [x] 2.2 让 runtime 在发起本地 tool 调用时统一生成 `call_id`、`depends_on_artifacts`、`trace_context` 与 `execution_mode`
- [x] 2.3 将 tool 执行结果统一回收为 `result envelope`，并把失败分流到结构化 `failure_type` 而不是自由文本异常
- [x] 2.4 在统一状态对象和 run trace 中补充 `tool_status`、`failure_type`、`streaming_mode`、`evidence_policy` 与 `produced_artifacts`

## 3. 现有能力适配为 Agent Tools

- [x] 3.1 以适配器方式封装 `catalog_lookup`，确保其输出 `paper_set` artifact、metadata provenance 和空结果 failure 语义
- [x] 3.2 以适配器方式封装 `fact_qa` 与 `cross_doc_summary`，补齐 evidence policy、流式声明和统一结果结构
- [x] 3.3 以适配器方式封装 `control`，明确其为非 citation 类 tool 并输出结构化控制结果
- [x] 3.4 以适配器方式封装 `paper_assistant`，声明前置条件、建议类 explanatory provenance 与研究辅助失败语义

## 4. 来源与 Evidence 约束

- [x] 4.1 扩展统一来源结构，显式区分 `citation`、`metadata` 与 `explanatory` provenance
- [x] 4.2 确保仅 `citation` 类型来源参与正文引用编号，目录、控制和中文化结果不得占用 citation 编号
- [x] 4.3 将 tool 的 `evidence_policy` 接入结果组装与 gate 入口，保证 `citation_required`、`citation_optional`、`citation_forbidden` 三类语义生效
- [x] 4.4 为 `paper_assistant` 的事实性结论与建议性内容实现分类型来源落盘与 trace 记录

## 5. 验证与文档

- [x] 5.1 增加 registry/schema 单元测试，覆盖未注册 tool、非法 failure type、非法 streaming/evidence 声明等校验场景
- [x] 5.2 增加 planner runtime 测试，覆盖 registry 解析、依赖产物透传、tool 级 trace 字段与结构化失败回退
- [x] 5.3 增加来源契约测试，覆盖 metadata/explanatory provenance 不参与正文 citation 编号
- [x] 5.4 更新运行时契约文档与相关开发说明，使后续 agent-first 变更可以基于统一 tool contract 扩展新能力
