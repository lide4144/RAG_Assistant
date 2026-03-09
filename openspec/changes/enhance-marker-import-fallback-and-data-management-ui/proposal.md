## 为什么

当前前端虽然已经支持部分 pipeline runtime 与 Marker tuning 配置，但仍缺少对 Marker `--use_llm` 服务族配置的可视化管理，导入过程中发生 LLM/解析失败降级时也缺少明确的前端提示，用户难以判断当前结果是否来自降级路径。与此同时，已有导入产物（尤其是 `data/indexes` 与 `data/processed` 相关数据）缺少可维护的前端管理入口，导致问题定位、重复处理与人工修复成本偏高。

## 变更内容

- 扩展前端配置能力，使用户可以在界面中管理 Marker 相关 LLM 服务配置，包括服务类型选择与不同 provider 所需的关键连接字段。
- 在导入失败或降级执行时，前端必须明确展示降级状态、原因与结果可信度提示，避免用户将降级结果误认为正常全量解析结果。
- 增强已有数据管理能力，使前端能够查看和管理已生成的 `Index` 与 `processed` 类产物，并支持结合运行状态进行问题排查。
- 升级相关前端界面的视觉表现，使用 Magic MCP 组件方案构建更高质量的状态卡片、降级提示区和数据管理面板，但不改变现有核心业务流程。

## 功能 (Capabilities)

### 新增功能
- `frontend-marker-artifact-management`: 提供对 `Index` 与 `processed` 类既有数据产物的可视化管理、状态查看与操作入口。

### 修改功能
- `frontend-llm-connection-settings`: 扩展设置页，使其支持 Marker LLM service 配置、provider 专属字段输入与可理解的保存反馈。
- `frontend-pipeline-ops-dashboard`: 增加导入失败降级态展示、降级原因可视化提示与更强的前端状态反馈。
- `marker-pdf-structured-parsing`: 补充 Marker 在使用 LLM 服务解析与降级时需要向前端暴露的状态与结果约束。
- `pipeline-runtime-config-persistence`: 扩展运行时配置持久化范围，使其覆盖 Marker 的 LLM service 选择与对应连接参数。

## 影响

- 前端设置页、知识处理页与可能新增的数据管理视图。
- Gateway/runtime overview 与 pipeline 配置读写接口，以及导入状态聚合返回结构。
- Marker 相关配置模型与运行态校验逻辑，包括 provider 特定字段映射。
- 端到端测试与视觉回归测试，尤其是导入降级、运行态提示和产物管理流程。
