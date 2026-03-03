## 新增需求

## 修改需求

### 需求:运行日志字段完整性
系统必须在运行轨迹中记录以下字段：输入问题、rewrite 后 query、retrieval top-k 及分数、expansion 追加 chunk、rerank top-n 及分数、最终决策与回答。系统在 ingest 启用可选清洗联动时，必须额外记录清洗启用状态、清洗输出路径、清洗成功状态与清洗错误信息（如有）。

#### 场景:阶段性结果已产生
- **当** 检索与重排阶段产生候选结果
- **那么** 运行 JSON 必须包含 top-k/top-n 结果与对应分数字段

#### 场景:阶段尚未启用
- **当** 某运行尚未启用 retrieval、expansion 或 rerank 阶段
- **那么** 系统必须保留对应字段并写入空数组或 null，而不得省略字段

#### 场景:ingest 开启联动清洗
- **当** ingest 以 `--clean` 运行
- **那么** 运行报告必须包含清洗相关字段（`clean_enabled`、`clean_output`、`clean_success`、`clean_error`）

### 需求:超参数集中配置
系统必须将关键超参数集中定义在 `configs/default.yaml`，至少包含 `chunk_size`、`overlap`、`top_k_retrieval`、`alpha_expansion`、`top_n_evidence`、`fusion_weight`、`RRF_k`、`sufficiency_threshold`。系统必须在加载后执行参数有效性校验，并对无效值给出告警与回退。系统必须保证可选 ingest 联动清洗在缺少清洗专用配置时仍可按默认行为运行。

#### 场景:运行时读取配置
- **当** pipeline 启动
- **那么** 系统必须从 `configs/default.yaml` 加载上述参数，并在运行中生效

#### 场景:配置值非法
- **当** 配置文件中出现越界或不合法参数值
- **那么** 系统必须记录告警并回退到安全默认值，而不是直接使用非法值

## 移除需求
