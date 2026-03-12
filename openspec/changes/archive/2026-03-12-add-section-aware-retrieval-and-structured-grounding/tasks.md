## 1. 结构产物

- [x] 1.1 在 Marker ingest 中定义并落盘章节树中间表示与 `structure_parse_status`
- [x] 1.2 为 section 节点补齐 `section_id`、层级路径、页码范围和 `child_chunk_ids` 映射
- [x] 1.3 增加结构解析质量门禁，阻止不可信章节树进入 structure index

## 2. 检索路由

- [x] 2.1 实现结构类问题识别与 `retrieval_route=section` 路由逻辑
- [x] 2.2 实现 section-aware retrieval，并在命中后补充关联 chunk 证据
- [x] 2.3 实现结构检索失败兜底，回退到既有 chunk 路径并记录 `structure_route_fallback`

## 3. 回答与门控

- [x] 3.1 引入结构化 claim -> chunk 绑定产物，并让最终回答优先从 claim 渲染
- [x] 3.2 调整 Evidence Policy Gate，优先校验 claim 绑定并排除列表编号/页码编号误判
- [x] 3.3 保持最终 citation 指向 chunk 证据，并补充 section 关联观测字段

## 4. 观测与验证

- [x] 4.1 扩展 `run_trace` 与 `qa_report`，记录结构解析状态、section 候选数、route/fallback 与 claim 绑定模式
- [x] 4.2 新增章节结构类回归测试，覆盖完整结构命中、局部结构命中与结构不可解析回退
- [x] 4.3 新增门控假阳性回归测试，覆盖 `1.`、`第 3 章`、`p.8` 等格式性数字
