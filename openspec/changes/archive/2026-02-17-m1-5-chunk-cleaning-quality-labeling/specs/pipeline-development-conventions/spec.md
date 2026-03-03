## 新增需求

### 需求:清洗产物约定
系统必须在 `data/processed/` 下维护清洗增强产物 `chunks_clean.jsonl`，并要求其字段结构可支持检索与证据引用。

#### 场景:清洗产物落盘
- **当** chunk 清洗流程完成
- **那么** 系统必须在 `data/processed/chunks_clean.jsonl` 落盘并可被后续模块读取

### 需求:检索阶段 table_list 降权策略
系统必须在融合打分阶段对 `content_type=table_list` 的 chunk 执行降权（默认乘以 `0.5`），但禁止将其从候选证据中直接剔除。

#### 场景:候选包含 table_list
- **当** 检索或重排候选中存在 `content_type=table_list` 条目
- **那么** 系统必须对其融合分数降权，并仍允许其进入证据集合

## 修改需求

### 需求:超参数集中配置
系统必须将关键超参数集中定义在 `configs/default.yaml`，至少包含 `chunk_size`、`overlap`、`top_k_retrieval`、`alpha_expansion`、`top_n_evidence`、`fusion_weight`、`RRF_k`、`sufficiency_threshold`。系统必须在加载后执行参数有效性校验，并对无效值给出告警与回退。系统还必须支持用于清洗与检索策略的可配置项（例如 `table_list_downweight`），并在缺失时回退到安全默认值。

#### 场景:运行时读取配置
- **当** pipeline 启动
- **那么** 系统必须从 `configs/default.yaml` 加载上述参数，并在运行中生效

#### 场景:配置值非法
- **当** 配置文件中出现越界或不合法参数值
- **那么** 系统必须记录告警并回退到安全默认值，而不是直接使用非法值

#### 场景:降权参数缺失
- **当** `table_list_downweight` 未配置
- **那么** 系统必须回退到默认值并保证检索流程可继续执行

### 需求:运行日志字段完整性
系统必须在运行轨迹中记录以下字段：输入问题、rewrite 后 query、retrieval top-k 及分数、expansion 追加 chunk、rerank top-n 及分数、最终决策与回答。系统在启用清洗与类型降权后，必须在运行日志中记录清洗命中统计与降权应用统计，以保证可复现性。

#### 场景:阶段性结果已产生
- **当** 检索与重排阶段产生候选结果
- **那么** 运行 JSON 必须包含 top-k/top-n 结果与对应分数字段

#### 场景:阶段尚未启用
- **当** 某运行尚未启用 retrieval、expansion 或 rerank 阶段
- **那么** 系统必须保留对应字段并写入空数组或 null，而不得省略字段

#### 场景:启用清洗与降权
- **当** 本次运行启用了 chunk 清洗和 `table_list` 降权
- **那么** 运行日志必须记录清洗规则命中数、短碎片合并数量与降权命中数量

## 移除需求
