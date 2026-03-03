## 为什么

项目已实现多个里程碑能力（M1~M3），但根目录缺少统一 README，导致新用户无法快速完成环境准备、数据处理、检索问答与常见命令调用。现在补齐 README，可降低使用门槛并减少重复沟通成本。

## 变更内容

- 在项目根目录维护 `README.md`，集中说明已实现功能、里程碑状态、目录结构与快速开始流程。
- 增加按里程碑分段的使用指南与命令示例（ingest / clean / index / qa）。
- 增加常见问题与排错建议（依赖、输入路径、输出位置、runs 日志查看）。
- 约定 README 的最小必备章节，后续里程碑变更时同步更新。

## 功能 (Capabilities)

### 新增功能
- `project-readme-guide`: 定义项目 README 的最小结构、内容要求与示例命令，确保用户可按文档完成端到端基础流程。

### 修改功能
- `pipeline-development-conventions`: 增加“项目文档维护约定”，要求关键里程碑完成后同步更新 README 的功能与示例。

## 影响

- 受影响文件：`README.md`（新增或重写）、`openspec/specs/project-readme-guide/spec.md`（新增）、`openspec/specs/pipeline-development-conventions/spec.md`（增量约束）。
- 对现有 API 与数据格式无破坏性变更。
- 对开发流程有正向影响：文档更新将成为里程碑交付的一部分。
