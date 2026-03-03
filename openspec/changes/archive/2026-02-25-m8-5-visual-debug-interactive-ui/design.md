## 上下文

当前 RAG 管线已具备 M1-M8 的 Python API 能力，但人工调试主要依赖 CLI 输出，难以快速确认“回答结论 <- 引用证据 <- 检索来源 <- Query 演变”链路是否一致。M8.5 需要在不引入复杂前端工程的前提下，提供一个轻量 UI（优先 Streamlit），直接消费现有 API 与 run trace，支持多轮交互和开发者审查。

关键约束：
- 不做登录鉴权、持久化数据库和复杂前端美化。
- 必须保留多轮会话语义并可显式清空（调用 `clear_session`）。
- 必须在同一轮可视化展示 query rewrite、calibrated query、evidence 分数和来源、Sufficiency Gate 降级原因。

## 目标 / 非目标

**目标：**
- 提供 `app/ui.py` 可直接运行的 Web 界面，支持多轮对话。
- 回答中的 `[1] [2] ...` 引用在 UI 中可交互查看对应证据。
- 侧边开发者面板展示本轮 trace：query 演变、evidence_grouped（含 `score_retrieval`、`score_rerank`、`source`）、降级告警（`reason`、`output_warnings`）。
- 支持“开启新对话/清空上下文”，并验证清空后检索不受旧会话污染。

**非目标：**
- 不引入账户体系、权限体系。
- 不引入复杂状态管理前端框架或自定义设计系统。
- 不建设线上持久化会话存储。

## 决策

### 决策 1：采用 Streamlit 作为默认 UI 运行时
- 方案 A（选中）：Streamlit 单文件页面（`streamlit run app/ui.py`）。
- 方案 B：Gradio 聊天界面。
- 理由：Streamlit 更适合同时渲染聊天区与 JSON Inspector，且支持侧边栏与状态缓存，能最快满足 M8.5 验收。

### 决策 2：以“消息 + 轮次 trace”双结构维护会话
- 方案 A（选中）：`st.session_state` 中维护 `chat_messages` 与 `turn_traces`，后端继续使用已有 `session_id`。
- 方案 B：仅保存渲染后的文本，不保存结构化 trace。
- 理由：Inspector 需要结构化字段高亮与回溯，必须保留每轮完整 trace 结构。

### 决策 3：引用交互采用“编号映射表 + 展开证据详情”
- 方案 A（选中）：解析回答中的 `[n]` 标记，映射到 `answer_citations[n-1]`，点击后在侧栏定位对应 evidence。
- 方案 B：仅显示纯文本引用，不可交互。
- 理由：M8.5 明确要求引用可交互；编号映射实现简单且不改变回答生成逻辑。

### 决策 4：Inspector 采用“标准化 trace 视图模型”
- 方案 A（选中）：UI 层将后端返回转换为统一视图模型，字段缺失时给出 `N/A`。
- 方案 B：直接原样 dump 全量 JSON。
- 理由：后端字段可能阶段性演进；视图模型可提高兼容性并保证关键字段总是可见。

## 风险 / 权衡

- [风险] 回答文本中的引用编号与 `answer_citations` 顺序不一致。  
  [缓解] 在渲染前做一致性校验；不一致时显示黄色 warning 并回退到 citation 列表展示。

- [风险] 旧 trace 字段缺失导致 Inspector 空白。  
  [缓解] 使用默认值占位，并在开发者面板显示“字段缺失”提示，不阻断聊天流程。

- [风险] 清空会话仅清空 UI 未清空后端状态，导致污染。  
  [缓解] 按钮动作必须先调用 `clear_session(session_id)` 成功后再重建本地状态。

- [风险] graph_expand 来源无法从 evidence 明确识别。  
  [缓解] 统一读取 evidence `source` 字段并增加显式标签（`graph_expand`）与颜色高亮。

## 迁移计划

1. 新增 `app/ui.py` 与最小 UI 适配层，复用现有 M1-M8 Python API。
2. 增加 UI 运行依赖（`streamlit`）并更新运行文档。
3. 在本地执行手工验收：
   - 启动 UI；
   - 发起含图扩展问题并核对 Inspector；
   - 点击“开启新对话”并验证无历史污染。
4. 若 UI 引发问题，回滚方式为不加载 `app/ui.py`，CLI 路径保持可用（低风险增量）。

## 开放问题

- 是否需要同时提供 Gradio 兼容入口，还是仅保留 Streamlit 单实现。
- 引用交互在 Streamlit 中采用点击按钮还是 hover 弹层，需结合易用性和实现复杂度最终确认。
