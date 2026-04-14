## 为什么

后端已完成从文件产物到 SQLite 论文存储的切换，论文生命周期状态（dedup→import→parse→clean→index→graph_build→ready）现已由数据库权威维护。但 Planner 模块（`app/planner_runtime.py`、`app/planner_policy.py` 等）仍依赖 `papers.json` 和临时状态推断来获取论文可用性与处理状态，这导致：

- Planner 无法准确判断某篇论文是否已准备好用于检索或问答
- 无法基于论文生命周期状态进行智能任务路由（如优先处理 failed 论文）
- 无法利用单篇论文级的重建/失败状态进行动态计划调整

必须在 Planner 层接入 SQLite 论文存储，使其能够基于权威生命周期状态做出决策。

## 变更内容

- 修改 `app/planner_runtime.py`，使其从 SQLite 查询论文状态（而非读取 `papers.json`），支持按生命周期状态筛选可用论文。
- 修改 `app/planner_policy.py`，增加基于论文生命周期状态的决策规则（如只使用 `ready` 状态论文、识别 `failed` 论文等）。
- 修改 Planner 的任务分解逻辑，使其能够在计划中体现论文级依赖（如等待某论文索引完成后再执行总结）。
- 为 Planner 提供查询论文重建/失败状态的接口，支持动态计划调整。
- **BREAKING**: Planner 不再以 `papers.json` 作为论文可用性的权威来源；必须查询 SQLite 获取准确的论文生命周期状态。

## 功能 (Capabilities)

### 新增功能
- `planner-paper-state-awareness`: 定义 Planner 如何感知和利用论文生命周期状态进行任务规划与路由决策。

### 修改功能
- `capability-planner-execution`: 计划执行必须能够基于论文生命周期状态确定可用论文范围，并在计划中处理论文级依赖。

## 影响

- 受影响代码包括 `app/planner_runtime.py`、`app/planner_policy.py` 及相关 Planner 链路。
- 受影响数据为 `papers.json` 的角色变化；Planner 将优先查询 SQLite。
- 受影响系统边界包括本地计划执行、论文级任务路由、失败重试策略。
- 新增内部依赖为论文域 SQLite 模式与生命周期状态模型；Planner 必须依赖数据库访问层获取论文状态。
