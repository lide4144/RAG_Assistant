## 新增需求
<!-- 如果有新增，请在此处添加完整的需求描述和场景。 -->

## 修改需求

### 需求:本地 Marker 解析能力
系统必须支持通过运行时配置控制 Surya/Marker 的显存敏感参数，至少包括 `RECOGNITION_BATCH_SIZE`、`DETECTOR_BATCH_SIZE`、`LAYOUT_BATCH_SIZE`、`OCR_ERROR_BATCH_SIZE`、`TABLE_REC_BATCH_SIZE` 与 `MODEL_DTYPE`。系统必须支持通过运行时配置启用 Marker `--use_llm` 及其 `llm_service`，并允许按服务保存 provider 所需的连接参数。系统必须在参数缺失或非法时回退到默认安全值；当 LLM 增强解析失败但基础解析仍可继续时，系统必须执行可审计的降级而不是整批中断。

#### 场景:使用 OpenAI 类服务运行 Marker LLM 解析
- **当** 管理员为 Marker 配置 `OpenAIService` 并提供 `openai_api_key`、`openai_model` 与可选 `openai_base_url`
- **那么** 系统必须以该服务执行 LLM 增强解析，并在运行记录中保留服务类型与生效字段摘要

#### 场景:Marker LLM 失败后降级继续
- **当** Marker LLM 服务不可达、鉴权失败或 provider 特定参数缺失，但基础解析链路可继续
- **那么** 系统必须记录降级原因、使用的回退路径与结果可信度说明，并继续完成可用的导入结果

### 需求:解析可观测性字段
系统必须在 ingest 报告中记录 Marker tuning 的生效值与来源（默认值/运行时配置/环境变量覆盖），用于定位显存瓶颈与性能退化原因。系统还必须记录 Marker LLM service、生效字段来源、是否启用 `--use_llm`、是否发生降级以及降级原因，供前端直接展示。

#### 场景:运行后审计 LLM 降级信息
- **当** 一次导入在 Marker LLM 增强阶段降级完成
- **那么** 报告必须包含 `llm_service`、`use_llm`、降级原因、降级后的执行路径与前端可显示的状态摘要

## 移除需求
<!-- 如果有移除，请在此处添加 -->
