## 1. UI 基础与运行入口

- [x] 1.1 创建 `app/ui.py` 基础页面结构，渲染对话区与开发者审查面板双区域布局
- [x] 1.2 接入 M1-M8 主问答 Python API，完成单轮提问到回答渲染的最小闭环
- [x] 1.3 补充/确认 `streamlit` 依赖与运行说明，确保 `streamlit run app/ui.py` 可启动

## 2. 多轮会话与清空机制

- [x] 2.1 在 UI 层维护 `session_id`、消息历史与轮次 trace 状态（基于 `st.session_state`）
- [x] 2.2 实现“开启新对话/清空上下文”按钮，并在点击时调用 `clear_session(session_id)`
- [x] 2.3 在清空动作后重建本地会话状态并校验新问题不携带旧历史（`history_used_turns=0` 或等效）

## 3. 引用交互与证据映射

- [x] 3.1 解析回答文本中的 `[n]` 引用标记并建立到 `answer_citations` 的稳定索引映射
- [x] 3.2 为每个引用提供可交互入口（点击或悬停），在审查面板展示对应 evidence 详情
- [x] 3.3 为映射失败场景增加降级提示（warning），避免将无效引用渲染为可追溯成功

## 4. Inspector Trace 与高亮审查

- [x] 4.1 在审查面板展示 Query 演变：`原始输入 -> Rewrite 结果 -> Calibrated Query`
- [x] 4.2 展示 `evidence_grouped` 并高亮 `score_retrieval`、`score_rerank`、`source`
- [x] 4.3 为 `source=graph_expand` 增加显式视觉标识，确保与 BM25/Dense 可区分
- [x] 4.4 当 `decision` 为 `refuse/clarify` 时，以醒目颜色展示 `reason` 与 `output_warnings`
- [x] 4.5 增加 trace 字段缺失的兜底显示（`N/A` + 提示），避免 UI 崩溃

## 5. 验收与回归检查

- [x] 5.1 执行 M8.5 启动验收：`streamlit run app/ui.py` 成功打开并可完成一次问答
- [x] 5.2 执行图扩展验收：提出含论文图扩展问题并确认 Inspector 可识别 `graph_expand` 证据
- [x] 5.3 执行会话隔离验收：清空后提无关问题，确认回答不受旧会话污染
- [x] 5.4 记录验收结果与已知限制，更新变更文档供 `/opsx:apply` 实施参考

## 6. 验收记录

- [x] 6.1 Streamlit 启动验证通过：`venv/bin/python -m streamlit run app/ui.py --server.headless true --server.port 8765`（沙箱外执行）
- [x] 6.2 图扩展样例验证通过：查询 `Graph expansion retrieval 在这个系统里如何扩展候选？` 命中 `graph_expand_count=1`（run: `runs/20260225_001215`）
- [x] 6.3 会话隔离验证通过：`clear_session` 后下一轮 `history_used_turns=0`（run: `runs/20260225_001126`）
- [x] 6.4 已知限制：当前环境中缺少 `SILICONFLOW_API_KEY` 时，默认配置会触发 embedding 路径错误；本次验收使用 `configs/m7_regression.yaml`（embedding 关闭）
