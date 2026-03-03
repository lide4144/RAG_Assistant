## 新增需求

## 修改需求

### 需求:目录结构约定
系统必须采用统一模块目录结构，至少包含 `app/ingest.py`、`app/index_bm25.py`、`app/index_vec.py`、`app/graph_build.py`、`app/retrieve.py`、`app/expand.py`、`app/rerank.py`、`app/judge.py`、`app/generate.py`，并保留 `data/`、`reports/`、`runs/` 目录。系统还必须在项目根目录维护 `README.md`，用于描述已实现功能与最小可运行示例。

#### 场景:初始化项目结构
- **当** 开发者初始化或整理代码结构
- **那么** 系统必须提供上述模块文件或等价占位实现，以保证后续里程碑扩展路径稳定

#### 场景:里程碑完成后更新说明文档
- **当** 新里程碑能力被实现并通过验收
- **那么** 系统必须同步更新根目录 `README.md` 的功能说明与命令示例

## 移除需求
