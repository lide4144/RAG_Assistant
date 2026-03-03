## 新增需求

### 需求:运行轨迹持久化
系统必须为每次运行创建 `runs/YYYYMMDD_HHMM/` 目录，并将本次运行的关键中间结果以 JSON 文件持久化。

#### 场景:运行完成后生成轨迹目录
- **当** 用户触发一次 pipeline 运行
- **那么** 系统必须在 `runs/` 下创建带时间戳的运行目录，并写入对应 JSON 轨迹文件

### 需求:运行日志字段完整性
系统必须在运行轨迹中记录以下字段：输入问题、rewrite 后 query、retrieval top-k 及分数、expansion 追加 chunk、rerank top-n 及分数、最终决策与回答。

#### 场景:阶段性结果已产生
- **当** 检索与重排阶段产生候选结果
- **那么** 运行 JSON 必须包含 top-k/top-n 结果与对应分数字段

#### 场景:阶段尚未启用
- **当** 某运行尚未启用 retrieval、expansion 或 rerank 阶段
- **那么** 系统必须保留对应字段并写入空数组或 null，而不得省略字段

### 需求:超参数集中配置
系统必须将关键超参数集中定义在 `configs/default.yaml`，至少包含 `chunk_size`、`overlap`、`top_k_retrieval`、`alpha_expansion`、`top_n_evidence`、`fusion_weight`、`RRF_k`、`sufficiency_threshold`。

#### 场景:运行时读取配置
- **当** pipeline 启动
- **那么** 系统必须从 `configs/default.yaml` 加载上述参数，并在运行中生效

### 需求:目录结构约定
系统必须采用统一模块目录结构，至少包含 `app/ingest.py`、`app/index_bm25.py`、`app/index_vec.py`、`app/graph_build.py`、`app/retrieve.py`、`app/expand.py`、`app/rerank.py`、`app/judge.py`、`app/generate.py`，并保留 `data/`、`reports/`、`runs/` 目录。

#### 场景:初始化项目结构
- **当** 开发者初始化或整理代码结构
- **那么** 系统必须提供上述模块文件或等价占位实现，以保证后续里程碑扩展路径稳定

## 修改需求

## 移除需求
