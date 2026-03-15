## 上下文

当前导入路径已经具备 Marker 首选解析与 legacy 回退能力，但标题决策函数仍把 `metadata`、Marker 候选和首页首行统一展开后按同一套规则打分。与此同时，Marker 原始输出中的 `block_type` 与 markdown 来源没有稳定穿透到统一中间表示，表格/公式类型也没有继续进入 retrieval weighting 与 citation。结果是系统虽然“使用了 Marker”，却没有真正“信任 Marker 的结构语义”，甚至在成功路径里丢掉了一部分结构语义。

当前问题主要分成四类：

1. Marker 已识别出正确主标题，但决策层把章节标题或摘要头选成最终标题。
2. 历史标题修复脚本只基于当前 `papers.json.title` 与 chunk 文本重算，无法复用原始结构化候选，导致修复能力受限。
3. Marker 已识别出表格、公式或 markdown 结构来源，但统一中间表示只保留 `text + heading_level`，下游无法判断哪些结构语义被保留、哪些已降级。
4. 即便结构语义被识别出来，当前 chunking、retrieval weighting 与 citation 仍基本按普通正文片段处理，无法表达“这是表格证据”或“这是公式证据”。

这次设计不改变 Marker 解析器的总体接入方式，也不引入外部元数据源；重点是把标题、block 语义和证据表达拉到同一条结构化消费链上。

## 目标 / 非目标

**目标：**
- 将标题选择策略改为“结构化信任”，让 Marker 成功解析时的标题层级成为第一证据源。
- 保留黑名单、长度规则和置信度阈值，但使其服务于结构化优先级，而不是覆盖来源优先级。
- 让导入报告和修复链路能区分“候选缺失”“候选被门禁拒绝”“候选存在但被更低优先级来源替代”。
- 让 Marker 成功路径中的关键结构语义进入统一中间表示，并继续贯通到 chunking、retrieval weighting 与 citation。
- 为历史标题修复提供可行的结构化重建路径。

**非目标：**
- 不在本变更中引入 DOI/Crossref 等外部在线元数据修复。
- 不在本变更中重写 Marker block 抽取算法或 chunker 总体策略。
- 不在本变更中重做前端 citation UI 或引入新的结构化渲染组件；本次重点在后端语义贯通与 citation contract。
- 不承诺自动修复所有历史脏标题；本次只定义修复路径和数据前提。

## 决策

1. 决策：标题来源采用分层信任，而不是来源无感知打分。
- 方案 A：保持所有来源同权，仅给 Marker 候选增加少量 bonus。
- 方案 B：只要有 Marker 候选就无条件采用。
- 方案 C（选中）：采用结构化信任阶梯，按 `Marker H1 -> Marker H2 -> Marker markdown 首行 -> metadata -> fallback_first_line` 依次尝试，每层内部再执行质量门禁与打分。
- 选择理由：A 无法消除当前误选根因；B 对错误结构标题过于脆弱；C 既体现 Marker 结构优先级，也保留局部门禁和安全回退。

2. 决策：门禁逻辑保留，但其职责从“全局裁决”收缩为“层内筛选”。
- 方案 A（选中）：黑名单、长度、作者尾巴裁剪、基础分值继续存在，但只用于筛选当前优先层中的候选。
- 方案 B：移除大部分门禁，完全依赖层级顺序。
- 选择理由：A 能阻断 `Abstract`、版权头、机构串等明显异常；B 会把错误结构化块直接落盘。

3. 决策：Marker 解析结果需要携带候选类别，而不是只暴露平铺字符串列表。
- 方案 A（选中）：在中间表示中区分 `h1_candidates`、`h2_candidates`、`markdown_first_line` 等语义来源。
- 方案 B：继续只返回 `title_candidates: list[str]`，在下游靠启发式猜测来源。
- 选择理由：A 让标题决策可解释、可观测、可测试；B 无法支撑“结构化信任”。

4. 决策：历史修复路径必须能够消费结构化标题信号。
- 方案 A（选中）：让重建脚本支持读取结构化候选或基于可重跑 Marker 重新生成候选，再沿同一决策树重算标题。
- 方案 B：继续用现有 `papers.json.title + chunk pages` 重算。
- 选择理由：B 本质上只能重复当前错误，不能称为修复。

5. 决策：Marker 成功后的结构语义要“保留并贯通”，而不是只“保留下来”。
- 方案 A（选中）：统一中间表示保留 block 语义和 markdown 来源诊断，并把表格/公式类型继续接入 chunking、retrieval weighting 与 citation provenance。
- 方案 B：先只保留 `block_type`，消费链路留到后续 change。
- 选择理由：A 才能让“Marker 成功”真正转化为用户侧可见收益；B 仍会把最有价值的结构信息停留在观测层。

6. 决策：citation contract 必须显式表达结构化证据 provenance。
- 方案 A（选中）：当证据来自表格/公式等结构化块时，在 citation 中保留对应 block provenance 和可读定位。
- 方案 B：继续把所有结构化块扁平为普通 chunk citation。
- 选择理由：A 能避免表格/公式证据在回答中被误表述为普通正文摘录；B 会削弱结构化解析的最终价值。

## 风险 / 权衡

- [风险] 某些 PDF 的 H1 标记可能错误，导致“过度信任”错误主标题。
  → 缓解措施：保留层内门禁；当 H1 全部被拒绝时自动降级到 H2/markdown/metadata。

- [风险] 标题来源字段变复杂后，前端或脚本可能无法立即消费新的诊断信息。
  → 缓解措施：保持现有 `title_source/title_confidence` 兼容，同时追加更细粒度的决策 trace 字段。

- [风险] 历史修复如果要求重跑 Marker，会放大运行成本。
  → 缓解措施：允许两条路径并存，优先消费已存在的结构化候选，缺失时才按需重跑。

- [风险] 结构化候选分类不稳会让设计落在“换了一层包装的启发式”。
  → 缓解措施：把候选类别来源限定为明确的 Marker 结构信号，不依赖模糊文本模式猜测。

- [风险] 表格/公式类型接入 retrieval weighting 后，可能导致排序震荡或误伤原本相关的正文 chunk。
  → 缓解措施：先采用温和加权和明确的回归样本，不做激进 hard filter。

- [风险] 结构化 citation provenance 增加后，旧消费者可能只识别普通 chunk citation。
  → 缓解措施：保持原有基础字段兼容，同时追加结构化 provenance 字段。

## Migration Plan

1. 扩展 Marker 中间表示，输出带类别的标题候选集合、block 语义与决策所需诊断字段。
2. 调整标题决策流程为分层尝试，层内执行门禁与打分，层间按结构化信任顺序降级。
3. 让 chunking 能识别并保留表格/公式等结构块语义，避免在 chunk 层完全扁平化。
4. 在 retrieval weighting 中接入结构块语义，定义表格/公式 chunk 的权重策略与回退行为。
5. 扩展 citation contract 与 QA 证据组装，使结构化证据带上 provenance 和可读定位。
6. 调整历史修复脚本与回归夹具，验证结构化信任路径能修复已知误选样本，且在缺少结构化输入时显式失败。
7. 如回归出现大面积 `Untitled` 增长、排序退化或 citation 兼容问题，可回滚到旧决策函数/旧加权/旧 citation 扩展字段，同时保留新增诊断字段以继续分析。

## Open Questions

- Marker 当前输出里，是否需要显式区分封面标题块与正文一级标题块，避免首页目录或 running header 混入 H1？
- 决策 trace 是只写 ingest 报告，还是也写入 `papers.json.ingest_metadata` 以支持后续修复与运营排查？
- 对已导入但无 Marker artifacts 的历史论文，默认修复路径是“跳过并标记需重跑”还是直接重跑 Marker？
- 表格/公式类型在 retrieval weighting 中更适合做轻度 boost/downweight，还是做 query-intent-aware gating？
- citation provenance 是扩展现有 chunk citation 字段，还是增加显式 `structure_provenance` 子对象更稳？
