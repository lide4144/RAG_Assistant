## 上下文

当前项目同时存在两类 LLM 连接：

- OpenAI-compatible 聊天/规划类连接：`answer`、`rewrite`、`planner`、`graph_entity`、`sufficiency_judge`
- 原生专用连接：`embedding`、`rerank`

之前的运行时配置在保存和展示上允许把 SiliconFlow 作为通用 provider 直接写入聊天/规划链路，但实际执行时这些链路经由 LiteLLM 或 OpenAI-compatible `/models` 约定运行。这样会让“保存成功”“运行态可用”“实际请求被 400 拒绝”同时出现，管理员难以判断问题来自配置读取还是 provider 语义。前端 Planner Runtime 也缺少模型探测后的下拉选择，和其他 stage 的管理体验不一致。

## 目标 / 非目标

**目标：**
- 为聊天/规划类运行时配置建立统一 provider 规范化语义。
- 保持 `embedding` 与 `rerank` 的原生 `siliconflow` 语义不被误改。
- 让 Planner Runtime 的保存、回显、运行态概览与执行链使用一致的 provider 解释。
- 让 Planner Runtime 配置区支持模型探测结果的下拉选择。

**非目标：**
- 不新增新的上游模型探测协议。
- 不把所有 provider 名称都折叠为单一值。
- 不改变 `embedding` 或 `rerank` 的原生接口协议。

## 决策

### 决策 1：按调用协议而不是品牌名划分 provider 语义
- 方案：对聊天/规划类 OpenAI-compatible 链路统一使用 `provider=openai` 表示兼容 OpenAI 的远端服务；`siliconflow` 仅保留给原生专用接口链路。
- 原因：真正决定兼容性的不是服务品牌，而是调用协议；这样可以让 LiteLLM、模型探测与运行态说明共享同一语义。
- 备选方案：继续允许聊天链路使用 `provider=siliconflow`。
  - 未选原因：会持续暴露 provider 解析不一致问题，并把实现细节泄漏到运行时配置语义中。

### 决策 2：在配置解析层做 provider 规范化，而不是把兼容逻辑分散到调用点
- 方案：在运行时配置保存、读取和回显层统一执行 provider alias 规范化，并按 stage 区分是否保留原生 provider。
- 原因：这样展示层、执行层和持久化文件看到的是同一套最终语义，避免局部修补后再次失配。
- 备选方案：只在 planner 或单个执行器里做特殊处理。
  - 未选原因：会继续留下其他 stage 的同类风险，并让规范无法稳定表达。

### 决策 3：Planner Runtime 复用既有模型探测接口
- 方案：Planner 配置区继续使用现有 `/api/admin/detect-models`，把探测结果纳入 Planner 模型下拉，不新增专用后端接口。
- 原因：Planner 的需求与其他 OpenAI-compatible 模型探测本质相同，复用现有接口成本最低且行为最一致。
- 备选方案：为 Planner 单独新增模型列表接口。
  - 未选原因：重复能力，没有新增协议价值。

## 风险 / 权衡

- [风险] 历史运行时配置文件中仍保存 `provider=siliconflow`
  - 缓解：读取与保存时统一执行 alias 规范化，允许旧值平滑迁移。
- [风险] 管理员误以为所有 SiliconFlow 场景都应切换为 `openai`
  - 缓解：在规范与前端语义中明确 `embedding`、`rerank` 保留原生 provider。
- [风险] Planner 模型下拉在未探测前没有足够选项
  - 缓解：保留当前已保存模型的回显，并允许探测后扩展可选列表。

## 迁移计划

1. 更新配置治理与 LLM 基础规范，明确 provider 规范化语义。
2. 更新 Planner Runtime 持久化与前端设置页规范，补充探测后选择行为。
3. 部署代码后允许旧配置在读取或再次保存时被规范化。
4. 若出现兼容问题，可回滚到上一提交；旧配置文件本身仍可被兼容读取。

## 开放问题

- 是否需要在前端文案中显式区分“OpenAI Compatible / SiliconFlow”与原生 `siliconflow` provider 标签。
- 是否需要后续为更多 OpenAI-compatible 服务增加同类 alias 规范化规则。
