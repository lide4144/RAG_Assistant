## 目的

定义论文入库及后续流水线开发的统一工程约定，确保运行可复现、参数可配置、目录结构一致。
## 需求
### 需求:运行轨迹持久化
系统必须为每次运行创建 `runs/YYYYMMDD_HHMM/` 目录，并将本次运行的关键中间结果以 JSON 文件持久化。系统必须保证同一分钟内多次运行也使用不同目录，禁止后一次运行覆盖前一次运行的轨迹文件。

#### 场景:运行完成后生成轨迹目录
- **当** 用户触发一次 pipeline 运行
- **那么** 系统必须在 `runs/` 下创建带时间戳的运行目录，并写入对应 JSON 轨迹文件

#### 场景:同一分钟连续运行
- **当** 在同一分钟内连续触发多次运行
- **那么** 系统必须为每次运行创建唯一目录（如秒级时间戳或冲突后缀）

### 需求:运行日志字段完整性
系统在 M2.2 QA 运行中必须额外记录 `calibrated_query`、`calibration_reason`、`query_retry_used`、`query_retry_reason`。系统还必须记录本次校准命中的意图类别与追加 cue words（可包含在 `calibration_reason` 中）。

#### 场景:M2.2 运行记录校准与重试
- **当** 用户执行带意图校准的 QA 检索
- **那么** runs JSON 必须完整记录校准字段、重试开关与重试原因（若触发）

### 需求:超参数集中配置
系统必须将关键超参数集中定义在 `configs/default.yaml`，至少包含 `chunk_size`、`overlap`、`top_k_retrieval`、`alpha_expansion`、`top_n_evidence`、`fusion_weight`、`RRF_k`、`sufficiency_threshold`。系统必须在加载后执行参数有效性校验，并对无效值给出告警与回退。系统必须保证可选 ingest 联动清洗在缺少清洗专用配置时仍可按默认行为运行。

#### 场景:运行时读取配置
- **当** pipeline 启动
- **那么** 系统必须从 `configs/default.yaml` 加载上述参数，并在运行中生效

#### 场景:配置值非法
- **当** 配置文件中出现越界或不合法参数值
- **那么** 系统必须记录告警并回退到安全默认值，而不是直接使用非法值

### 需求:目录结构约定
系统必须采用统一模块目录结构，至少包含 `app/ingest.py`、`app/index_bm25.py`、`app/index_vec.py`、`app/graph_build.py`、`app/retrieve.py`、`app/expand.py`、`app/rerank.py`、`app/judge.py`、`app/generate.py`，并保留 `data/`、`reports/`、`runs/` 目录。系统还必须在项目根目录维护 `README.md`，用于描述已实现功能与最小可运行示例。

#### 场景:初始化项目结构
- **当** 开发者初始化或整理代码结构
- **那么** 系统必须提供上述模块文件或等价占位实现，以保证后续里程碑扩展路径稳定

#### 场景:里程碑完成后更新说明文档
- **当** 新里程碑能力被实现并通过验收
- **那么** 系统必须同步更新根目录 `README.md` 的功能说明与命令示例

### 需求:标准 YAML 配置解析
系统必须使用标准 YAML 解析机制读取 `configs/default.yaml`，并禁止依赖简化行解析作为主路径。

#### 场景:YAML 包含注释与复杂空白
- **当** 配置文件包含注释、空行或常见 YAML 格式细节
- **那么** 系统必须能够正确解析并加载配置值

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

### 需求:M2 基线评估记录
系统必须生成 `reports/m2_baseline.md`，至少记录 10 个问题的 QA 输出与证据，并标注每个问题使用的检索模式。

#### 场景:完成基线评估后落盘
- **当** 用户完成 M2 基线问题集评估
- **那么** 系统必须在 `reports/m2_baseline.md` 写入不少于 10 条问题记录及对应 evidence

### 需求:M2.1 策略评估记录
系统必须生成 `reports/m2_1_policy.md`，并至少记录 5 个“指代不明问题”的处理结果（rewrite 或 clarify）以及 5 个“作者/机构类问题”的条件放行验证结果。

#### 场景:完成 M2.1 评估后落盘
- **当** 用户完成 M2.1 策略评估
- **那么** 系统必须在 `reports/m2_1_policy.md` 写入不少于 10 条评估记录，并标注处理策略与证据摘要

### 需求:M3 改写评估记录
系统必须生成 `reports/m3_rewrite_eval.md`，至少记录 30 个问题在“改写前/改写后”的检索对比结论，并明确标注至少 10 个问题 evidence 相关性提升样例。

#### 场景:完成 M3 评估后落盘
- **当** 用户完成 M3 rewrite 评估
- **那么** 系统必须在 `reports/m3_rewrite_eval.md` 写入对比记录与改进样例

### 需求:M2.2 评估记录
系统必须生成 `reports/m2_2_intent_calibration.md`，至少记录 10 条问题的 `Q`、`rewritten_query`、`calibrated_query`、是否 retry、Top-5 evidence 与 summary shell 占比统计。

#### 场景:完成 M2.2 评估后落盘
- **当** 用户完成 M2.2 问题集评估
- **那么** 系统必须在 `reports/m2_2_intent_calibration.md` 写入不少于 10 条记录并可复现校准行为

### 需求:M2.3 输出一致性日志记录
系统在 M2.3 QA 运行中必须记录 `answer_citations` 与 `output_warnings`，并确保 warning 可用于回放异常修复过程（例如 top_paper 补证据、证据不足降级、summary shell 仍主导）。

#### 场景:M2.3 输出治理字段落盘
- **当** QA 流程完成回答输出
- **那么** 对应 runs JSON 必须落盘 citation 与 warning 字段，且字段可用于复现本次输出决策

### 需求:M2.3 评估记录
系统必须生成 `reports/m2_3_output_consistency.md`，至少记录 10 条问题的 `Q`、`scope_mode`、`calibrated_query`、`papers_ranked(top5)`、`evidence_grouped`、`answer`、`answer_citations`、`output_warnings`，并包含 3 个 M2.2 与 M2.3 的对比案例。

#### 场景:完成 M2.3 评估后落盘
- **当** 用户完成 M2.3 问题集评估
- **那么** 系统必须在 `reports/m2_3_output_consistency.md` 写入不少于 10 条记录与 3 条对比案例

