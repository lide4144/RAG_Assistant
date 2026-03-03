## 为什么

当前系统核心 RAG 能力完整，但前端交互与产品化形态仍以 Streamlit 审查视角为主，用户无法获得接近 Perplexica 的“搜索助手”体验（模式切换、实时流式、来源卡片、连续追问）。若继续在现有 UI 上做局部修补，体验提升空间有限，且难以承载后续联网检索编排能力。

同时，现有算法链路在 rewrite、intent、sufficiency 等环节存在较多硬规则拦截，容易覆盖 embedding/reranker 的语义能力，导致检索查询被过度词法化、回答风格保守且简化。GraphRAG 虽在召回链路生效，但 UI 仅显示 `graph_expand` 标签，缺少图结构可视化与可解释路径。

现在需要引入更贴近目标产品的技术栈与分层架构，在保留现有 Python RAG 资产的前提下，完成体验层和编排层升级。

## 变更内容

- 新建面向搜索助手体验的前端技术栈：采用 Next.js + React + Tailwind 构建产品化聊天界面。
- 引入 Node 网关（BFF）作为统一实时通信与编排入口，提供 WebSocket 流式消息协议。
- 将现有 Python QA/RAG 链路下沉为“智能内核服务”，由网关调用，避免一次性重写。
- 在 V1 提供 `Local / Web / Hybrid` 三模式用户可控入口，统一回答流式输出与引用呈现。
- 建立统一来源与引用协议，支持本地证据与 Web 来源共存、编号一致、可点击追溯。
- 对算法链路做“语义优先、规则护栏”重构：降低硬规则阻断，改为打分仲裁与约束修补；升级回答生成 prompt 与结构化输出策略。
- 补齐 GraphRAG 在产品层的可视化表达：提供检索子图、路径解释与证据节点联动。
- 明确分阶段迁移策略：先体验壳层替换，再扩展联网编排与模式细分。

## 功能 (Capabilities)

### 新增功能
- `perplexica-like-chat-experience`: 产品化聊天体验层，支持流式消息、模式切换、来源卡片与连续追问。
- `node-gateway-orchestration`: Node 网关编排层，统一 WebSocket 协议、路由策略与多后端调用。
- `unified-source-citation-contract`: 统一来源与引用契约，覆盖本地 chunk 与 web URL 的同构展示。
- `graphrag-visual-observability`: GraphRAG 可视化与路径可解释能力，支持子图浏览与证据联动定位。

### 修改功能
- `visual-debug-interactive-ui`: 从“开发者审查优先”扩展为“用户体验优先 + 审查能力可保留在开发面板”。
- `research-assistant-workbench`: 交互入口从单一 Streamlit 页面升级为产品化前端壳层，保留研究助手工作流语义。
- `llm-answer-streaming-delivery`: 流式输出通道从单实现路径扩展为经网关统一分发的多源流式协议。
- `query-rewriting`: 从硬规则主导升级为语义改写主导 + 规则约束修补的混合策略。
- `sufficiency-gate`: 从高频澄清/拒答倾向调整为“可追溯部分回答优先”的门控策略。
- `llm-generation-foundation`: 升级回答 prompt 结构与引用绑定流程，提升答案质量与可读性。

## 影响

- 受影响代码：新增前端应用目录（Next.js）、新增 Node 网关服务目录；`app/qa.py`、`app/rewrite.py`、`app/intent_calibration.py`、`app/sufficiency.py` 与会话/流式相关模块需提供网关调用接口并调整策略。
- 受影响接口：新增 WebSocket 事件协议（`message`/`sources`/`messageEnd`/`error`）与网关到内核服务调用契约。
- 受影响交互：新增 GraphRAG 子图可视化面板与证据联动交互，明确默认展示策略与性能边界。
- 受影响运行方式：本地开发从“单进程 Streamlit”为主，转为“前端 + 网关 + Python 内核”多进程协同。
- 兼容性影响：Streamlit 现有调试能力需规划保留或迁移路径，避免调试能力回退。
