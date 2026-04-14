# planner-paper-state-awareness 规范

## 目的

定义 Planner 如何感知和利用论文生命周期状态进行任务规划与路由决策，使 Planner 能够基于 SQLite 论文存储中的权威状态做出准确的论文可用性判断。

## 需求

### 需求:Planner 必须能够查询论文生命周期状态
Planner 必须能够通过数据库访问层查询论文的生命周期状态（`dedup`、`import`、`parse`、`clean`、`index`、`graph_build`、`ready`、`failed`、`rebuild_pending`），以便在规划时准确判断论文可用性。

#### 场景:Planner 筛选 ready 状态的论文
- **当** Planner 需要确定哪些论文可用于检索或问答
- **那么** Planner 必须查询 SQLite 并仅选择状态为 `ready` 的论文

#### 场景:Planner 识别 failed 论文
- **当** Planner 发现某篇论文状态为 `failed`
- **那么** Planner 必须在计划中标记该论文不可用，并可建议用户重试

### 需求:Planner 必须支持基于论文状态的智能路由
Planner 必须能够根据论文生命周期状态进行智能任务路由，如优先处理待重建论文、跳过未就绪论文等。

#### 场景:Planner 优先处理 rebuild_pending 论文
- **当** 用户请求涉及待重建论文
- **那么** Planner 可以建议在执行主任务前先重建这些论文

#### 场景:Planner 识别索引未完成的论文
- **当** 某篇论文状态为 `imported` 或 `parsed` 但尚未 `ready`
- **那么** Planner 必须等待或提示用户该论文暂不可用

### 需求:Planner 必须能够在计划中表达论文级依赖
Planner 必须能够在生成的 action plan 中表达论文级别的依赖关系，如等待某论文索引完成后再执行总结。

#### 场景:Planner 生成带论文依赖的多步计划
- **当** 用户请求需要先确认论文可用再执行总结
- **那么** Planner 必须生成包含论文状态检查依赖的 action plan

### 需求:Planner 必须能够查询论文重建/失败状态
Planner 必须能够查询论文的重建状态（`rebuild_pending`）和失败原因，以支持动态计划调整。

#### 场景:Planner 查询论文失败原因
- **当** 某篇论文状态为 `failed`
- **那么** Planner 必须能够获取失败原因并在计划中体现

#### 场景:Planner 获取待重建论文列表
- **当** 用户请求批量处理待重建论文
- **那么** Planner 必须能够查询所有 `rebuild_pending` 状态的论文
