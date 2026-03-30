## 新增需求

无

## 修改需求

### 需求:系统必须在探测成功后提供模型选择
系统必须在模型探测成功后展示模型下拉框，并禁止在未探测成功时展示无效模型选项。该要求同时适用于核心 stage 配置区与独立的 Planner Runtime 配置区；Planner Runtime 不得退化为仅支持手填模型名的单独表单。

#### 场景:探测成功
- **当** 后端返回至少一个可用模型
- **那么** 系统必须显示模型下拉并允许管理员选择目标模型

#### 场景:Planner Runtime 探测成功
- **当** 管理员在 Planner Runtime 配置区完成连接测试并拿到模型列表
- **那么** 页面必须为 Planner Runtime 显示模型下拉，并允许从探测结果中选择 planner model

### 需求:系统必须支持 Provider 预设联动
系统必须在管理员选择 Provider 后自动填充推荐 API Base，且必须允许管理员在自动填充后手动覆盖。对于聊天、规划和其他 OpenAI-compatible 配置链路，前端还必须优先使用协议语义表达 provider，并在需要展示具体服务商时通过预设文案或 API Base 辅助说明，而不是把服务商品牌名直接当作通用 provider 持久化。对于 `embedding` 与 `rerank` 这类原生专用链路，前端必须允许保留原生 provider 选项。

#### 场景:选择服务商
- **当** 管理员在 Provider 下拉框中选择某服务商
- **那么** 系统必须自动填充推荐 API Base 并允许后续修改

#### 场景:选择 OpenAI-compatible 服务商
- **当** 管理员为 `answer`、`rewrite`、`planner`、`graph_entity` 或 `sufficiency_judge` 选择 SiliconFlow 等 OpenAI-compatible 上游
- **那么** 前端必须按 OpenAI-compatible 语义保存 provider，并同时保留服务商预设带来的推荐 API Base 与模型探测能力

#### 场景:选择原生专用服务商
- **当** 管理员为 `embedding` 或 `rerank` 选择 SiliconFlow
- **那么** 前端必须允许保留原生 `siliconflow` provider，而不得统一改写为 OpenAI-compatible provider

### 需求:系统必须在设置页明确区分运行时设置与系统基线
系统必须在“模型设置”页面中明确向管理员表达当前页面管理的是运行时可调整配置，而不是全量系统配置。页面必须对不在前端覆盖范围内的系统基线配置保持边界清晰，禁止让管理员误以为页面中展示的设置已囊括 `default.yaml` 或全部系统设置。页面同时必须将 `sufficiency_judge` 证据充分性判定小模型纳入运行时可管理范围，使管理员无需编辑 YAML 即可调整该小模型的连接参数；并必须为 `planner` 提供独立的高风险运行时配置面，使管理员可以承担顶层规划模型的成本与切换责任。

#### 场景:管理员进入设置页理解页面边界
- **当** 管理员打开“模型设置”页面
- **那么** 页面必须能够清楚表达其管理范围属于运行时设置，并提示系统基线配置不在本页全量呈现

#### 场景:管理员调整证据充分性判定小模型
- **当** 管理员需要调整 `sufficiency_judge` 的 provider、api_base、api_key 或 model
- **那么** 系统必须在“模型设置”页面提供对应运行时配置入口，并在保存后回显当前生效来源

#### 场景:管理员调整顶层 Planner Runtime 模型
- **当** 管理员需要调整 `planner` 的启用状态、provider、api_base、api_key、model 或 timeout
- **那么** 系统必须在“模型设置”页面提供独立高风险配置区，而不是将其混入普通 stage 卡片，并在保存后回显当前生效来源

#### 场景:管理员从历史配置进入 Planner Runtime 设置
- **当** Planner Runtime 已保存历史模型值但尚未重新执行模型探测
- **那么** 页面必须仍能回显该模型并允许后续在探测成功后切换到新的可选模型

## 移除需求
