## 上下文

现有前端具备 `/api/admin/llm-config` 的读写能力，但该能力主要用于编辑，不提供跨页面的运行态可视化。聊天页仅使用 `configured` 布尔值，无法回答“到底在用哪个模型”。

同时，Marker 相关参数目前主要依赖静态配置与环境变量，缺乏统一的 runtime 管理入口。

## 目标 / 非目标

**目标：**
- 在不实现业务代码改造的前提下明确一套“可观察的模型运行态”信息架构。
- 允许通过前端调整 Marker/Surya 的显存敏感参数并可回显。
- 将模型可见性从“设置页内”扩展到“全局壳层 + 业务页上下文”。

**非目标：**
- 不在本变更中引入自动压测或自动 profile 选择算法。
- 不在本变更中改造 LLM 路由策略本身。

## 决策

1. 决策：新增“运行态概览接口”，而不是由前端拼接多个接口。
- 方案 A（选中）：`GET /api/admin/runtime-overview` 返回聚合视图。
- 方案 B：前端并发调用 `llm-config` + `pipeline-config` 自行组装。
- 理由：A 降低前端状态拼装复杂度，便于统一状态分级规则。

2. 决策：Marker 参数持久化采用独立 runtime 配置域。
- 方案 A（选中）：新增 pipeline runtime 配置持久化能力。
- 方案 B：混入已有 `llm_runtime_config.json`。
- 理由：A 职责边界更清晰，避免 LLM 与 ingest 参数耦合。

3. 决策：前端信息分层采用“全局条 + 页面卡片”。
- 全局：壳层只读摘要，突出当前状态。
- 页面：聊天/设置提供上下文化详细信息。

## 数据草图

```text
RuntimeOverview
├─ llm
│  ├─ answer: {provider, model, configured}
│  ├─ embedding: {...}
│  ├─ rerank: {...}
│  ├─ rewrite: {...}
│  └─ graph_entity: {...}
├─ pipeline
│  └─ marker_tuning:
│     ├─ recognition_batch_size
│     ├─ detector_batch_size
│     ├─ layout_batch_size
│     ├─ ocr_error_batch_size
│     ├─ table_rec_batch_size
│     └─ model_dtype
└─ status
   ├─ level: READY | DEGRADED | BLOCKED | ERROR
   └─ reasons: []
```

## 状态分级建议

- `READY`：必需 stage 与 marker tuning 均有效。
- `DEGRADED`：部分可选 stage 缺失或使用回退默认值。
- `BLOCKED`：关键路径不可用（例如 answer 未配置）。
- `ERROR`：概览接口不可用或配置非法。

## 风险 / 权衡

- [风险] 配置项增加导致误配置概率上升。
  → 缓解：设置页提供“8GB 安全档位”快捷填充与范围校验。

- [风险] 全局状态条信息过载。
  → 缓解：全局仅显示摘要，详情下沉到聊天与设置页面。

- [风险] 环境变量与 runtime 配置冲突。
  → 缓解：定义明确优先级并在概览中显示 `effective_source`。

## Migration Plan

1. 增加 pipeline runtime 配置模型与校验。
2. 增加 `runtime-overview` 聚合接口。
3. 调整前端壳层与聊天页读取概览并展示。
4. 在设置页增加 Marker tuning 可视化与可编辑区。
5. 补充回归测试与运维文档。

回滚策略：
- 保留旧 `/api/admin/llm-config` 行为不变；
- pipeline runtime 配置缺失时自动回退默认值；
- 前端概览失败时降级为当前页面原有提示。

## Open Questions

- marker tuning 是否允许按“设备档位”（8G/16G/24G）预设切换？
- `model_dtype` 是否限制为 `float16/float32`，还是允许 `bfloat16`（跨设备兼容差异）？
- `runtime-overview` 是否要附带最近一次 ingest 的观测摘要（fallback 率）？
