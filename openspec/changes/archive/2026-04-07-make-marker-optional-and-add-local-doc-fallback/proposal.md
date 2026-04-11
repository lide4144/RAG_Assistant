## 为什么

当前项目虽然已经支持 `marker unavailable -> legacy parser` 的回退，但整体产品姿态仍然偏向 `marker-first`：

- 默认配置仍启用 `marker_enabled=true`
- 主依赖安装路径仍会尝试安装 `marker-pdf`
- 前端设置页缺少“是否启用 Marker 结构化解析”的显式总开关

这导致在个人电脑或低资源环境中，用户即使只需要“先把本地文档导入并可检索”，也会被 Marker 的安装、显存/内存与运行复杂度拖住。相比之下，`example_projects/LightRAG` 的本地文档处理策略更偏向“默认轻量解析，可选增强解析，失败自动降级”，更适合作为当前项目的默认本地体验。

## 变更内容

- 将 Marker 从默认主路径调整为可选增强能力：系统默认走轻量本地解析路径，只有在用户显式开启 Marker 时才尝试结构化解析。
- 在前端设置页新增 Marker 总开关，并明确展示当前模式是“基础解析”还是“增强解析”。
- 在后端引入参考 `example_projects/LightRAG` 的本地降级处理逻辑：先判断增强解析器是否启用且可用，不可用时自动回退到按文件类型选择的轻量解析路径，而不是把增强解析作为导入前提。首版设计必须覆盖多种常见本地文档类型，而不是只围绕 `pdf/docx` 建模。
- 保持现有 Marker observability 与 fallback trace，但其语义从“默认主路失败后的兜底”调整为“用户启用增强后的受控降级”。

## 功能 (Capabilities)

### 修改功能
- `marker-pdf-structured-parsing`: Marker 必须改为显式启用的可选增强路径，而非默认本地主路径。
- `paper-ingestion-pipeline`: 本地文档导入必须采用“默认轻量解析 + 可选增强解析 + 自动降级”的处理模型。
- `library-quick-ingestion`: 本地导入入口必须从“只接收 PDF”扩展为可按文件类型路由的统一入口，至少为后续 `pdf/docx/pptx/xlsx/txt/md/html/csv/json/xml/yaml` 等类型保留一致的受理与错误语义。
- `frontend-llm-connection-settings`: 设置页必须新增 Marker 总开关，并展示当前启用状态与风险说明。
- `frontend-pipeline-ops-dashboard`: 当导入走增强解析降级路径时，前端必须区分“增强失败后降级完成”和“普通基础解析”两种语义。

## 影响

- 后端配置模型、依赖拆分方式与 ingest 路由逻辑。
- 前端设置页、运行态概览与导入工作台的状态表达。
- 本地开发文档、安装说明与导入故障排查文档。
- 与 Marker 默认启用假设相关的测试、脚本与回归用例。
