## 新增需求
<!-- 如果有新增，请在此处添加完整的需求描述和场景。 -->

## 修改需求

### 需求:系统必须支持保存最终配置
系统必须支持在模型设置页中编辑并保存 Marker/Surya 运行档位参数，包括 `recognition_batch_size`、`detector_batch_size`、`layout_batch_size`、`ocr_error_batch_size`、`table_rec_batch_size`、`model_dtype`，并必须同时支持 Marker `--use_llm` 所需的服务配置，包括 `llm_service` 选择以及 provider 所需的连接字段；保存后必须回显最新生效值。

#### 场景:保存 Marker LLM 服务配置
- **当** 管理员启用 Marker LLM 增强并选择 `Gemini`、`Google Vertex`、`Ollama`、`Claude`、`OpenAI` 或 `Azure OpenAI`
- **那么** 系统必须展示该服务所需字段、完成校验并在保存成功后回显当前生效配置

#### 场景:切换服务时更新表单
- **当** 管理员切换 Marker LLM service
- **那么** 系统必须仅展示当前服务需要的字段，并保留同一次编辑会话中尚未保存的相关输入

### 需求:系统必须提供可理解的错误反馈
系统必须根据后端错误码展示可理解提示，禁止仅显示无上下文的通用失败文案；对于密钥错误、网络失败、模型不可用等常见错误必须给出可执行指引；当 Marker LLM service 缺少特定 provider 必填字段时，系统必须定位到具体字段并说明缺失原因。

#### 场景:保存 Marker LLM 配置缺少必填字段
- **当** 管理员保存 `Google Vertex` 但未填写 `vertex_project_id`
- **那么** 系统必须在对应字段显示错误说明，并保留其他已填写输入

### 需求:系统必须提供模型连接设置的保存反馈
系统必须在“测试并保存”操作期间显示加载状态，并必须在保存成功后给出 Toast 成功提示；对于 Marker LLM service 配置，系统还必须在保存后显示当前配置是“直连生效”“降级可用”还是“未启用”。

#### 场景:Marker LLM 服务保存成功
- **当** 管理员保存 Marker LLM service 配置且后端返回成功
- **那么** 页面必须展示成功反馈，并在概览区显示当前服务状态与生效摘要

## 移除需求
<!-- 如果有移除，请在此处添加 -->
