## 上下文

当前系统运行时配置面板仅显式管理 `answer/embedding/rerank` 三段，且 `rewrite` 在配置加载时被强制映射到 `answer` 路由，`graph_entity_llm_*` 仍停留在静态配置。对“外部 API + 本地混合”运维场景而言，这会带来三类问题：配置面不完整、路由耦合难以回滚、个人开发机本地化落地成本高。

本次变更以 8GB 显存开发机为约束，目标是在不破坏既有外部 API 路由的前提下，将 `embedding/rewrite` 设为可本地优先，为 `rerank` 保留远端兼容默认值，并补齐前端全模型配置管理。

## 目标 / 非目标

**目标：**
- 提供统一“全模型配置”管理能力，覆盖 `answer/embedding/rerank/rewrite/graph_entity` 关键位点。
- 将 `rewrite` 从“隐式跟随 answer”调整为独立可配置、可持久化、可回滚。
- 定义本地模型默认档位与安装路径（Ollama 主路径），确保单机可复现。
- 建立可执行验收口径：连通性、基础质量回归、回滚可操作性。

**非目标：**
- 不在本变更中重写 QA 主回答链路或强制 `answer` 本地化。
- 不在本变更中引入复杂多节点调度（K8s、多机弹性扩缩容）。
- 不在本变更中追求全模型最优 benchmark，只要求“可用且可回滚”。

## 决策

1. 决策：本地部署主路径使用 Ollama，vLLM 作为可选高级路径。
- 方案 A（选中）：文档、默认值、运维脚本以 Ollama 为主。
- 方案 B：双主路径并行（Ollama 与 vLLM 同等首选）。
- 选择理由：A 对个人开发机门槛更低，减少首轮交付复杂度。

2. 决策：前端模型设置升级为“全模型配置”而非仅补 rewrite。
- 方案 A（选中）：一次性补齐关键位点（answer/embedding/rerank/rewrite/graph entity）。
- 方案 B：只在现有面板加 rewrite，其他继续静态配置。
- 选择理由：A 可避免二次 UI/接口重构，降低后续运维认知成本。

3. 决策：runtime 配置结构显式增加 rewrite 与 graph entity 路由项。
- 方案 A（选中）：扩展运行时配置模型并保持旧载荷兼容。
- 方案 B：继续使用 answer 覆盖 rewrite，graph entity 维持静态。
- 选择理由：A 能消除耦合隐式行为并提升可观测性。

4. 决策：默认本地模型档位固定为“轻量优先”，仅覆盖 Ollama 主路径中可稳定落地的位点。
- embedding: `bge-m3`（备选 `nomic-embed-text`）
- rewrite: `qwen2.5:3b`（备选 `qwen2.5:1.5b`）
- rerank: 默认不纳入 Ollama 主路径，保留远端兼容模型（例如 `Qwen/Qwen3-Reranker-8B`）
- 选择理由：Ollama 可直接拉取的官方 tag 与 8GB 设备约束共同决定了 embedding/rewrite 更适合作为首轮本地默认，rerank 则保留远端路径更稳。

## 风险 / 权衡

- [风险] 本地模型格式与推理引擎兼容性不一致（尤其 rerank）。
  → 缓解措施：从 Ollama 主路径中移除 rerank 默认值，提供模型兼容矩阵与降级映射，允许回退外部 API。

- [风险] 前端一次性扩展全模型字段可能增加用户输入复杂度。
  → 缓解措施：默认折叠高级位点，提供“推荐默认值一键填充”。

- [风险] rewrite 独立后，线上行为可能与历史“跟随 answer”出现偏差。
  → 缓解措施：增加行为对比回归，默认迁移值先与 answer 对齐再允许单独覆盖。

- [风险] graph entity 改为前端可配后，离线构图稳定性受本地模型波动影响。
  → 缓解措施：保留静态默认与任务级失败回退，不因单项失败中断整体流程。

## Migration Plan

1. 扩展运行时配置数据结构与 API 契约，新增 rewrite/graph entity 配置位点并保持旧字段兼容。
2. 改造配置加载逻辑，移除 rewrite 强绑定 answer 的覆盖行为，改为显式读取 rewrite 路由。
3. 前端模型设置面板升级为全模型配置，增加本地两段默认值与远端 rerank 默认值预填策略。
4. 新增本地模型安装文档与脚本入口（Ollama 主路径），覆盖 embedding/rewrite 拉取、启动、健康检查。
5. 执行回归：保存回显、embedding/rewrite 连通性探测、rewrite 行为对齐、本地不可用降级、回滚验证。

回滚策略：
- 配置层：恢复到外部 API 默认 provider/api_base/model；
- 运行层：保留旧载荷兼容分支；
- 前端层：保留三段最小配置提交能力作为兜底。

## Open Questions

- `graph entity` 在前端中是否默认展开，还是仅在“高级设置”中显示？
- rerank 本地部署是否统一走同一推理后端，还是允许独立 endpoint？
- 本地 rewrite 的最大上下文与超时阈值采用统一值还是按 provider 细分？
