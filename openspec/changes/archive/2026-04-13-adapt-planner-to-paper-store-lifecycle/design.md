## 上下文

后端已完成从文件产物到 SQLite 论文存储的切换（`refactor-backend-for-paper-store-lifecycle`），论文生命周期状态（dedup→import→parse→clean→index→graph_build→ready）现已由数据库权威维护。

但 Planner 模块（`app/planner_runtime.py`、`app/planner_policy.py` 等）仍通过以下方式获取论文状态：
- 直接读取 `papers.json` 文件
- 依赖临时状态推断
- 无法感知单篇论文级的重建/失败状态

这导致 Planner 无法：
- 准确判断某篇论文是否已准备好用于检索或问答
- 基于论文生命周期状态进行智能任务路由
- 利用单篇论文级的重建/失败状态进行动态计划调整

约束如下：
- 不能改变 Planner 的核心架构和运行时契约
- 需要保持现有 tool 调用契约不变
- 必须平滑过渡，不能影响现有功能

主要利益相关者包括：
- 聊天/问答用户，需要准确的论文可用性判断
- 开发团队，需要清晰的 Planner 与存储层边界
- 运维团队，需要可观测的论文状态流转

## 目标 / 非目标

**目标：**

- 让 `app/planner_runtime.py` 从 SQLite 查询论文状态（而非读取 `papers.json`）
- 让 `app/planner_policy.py` 增加基于论文生命周期状态的决策规则
- 为 Planner 提供查询论文重建/失败状态的接口
- 修改 Planner 的任务分解逻辑，使其能够处理论文级依赖
- 保持现有 Planner API 契约不变

**非目标：**

- 不要求重写 Planner 的核心架构
- 不要求改变 tool registry 的注册契约
- 不要求在首阶段实现复杂的论文级依赖图

## 决策

### 决策 1：Planner 通过 paper_store 模块查询论文状态

`app/planner_runtime.py` 及相关模块将通过 `app.paper_store` 模块与 SQLite 交互，不再直接操作 `papers.json`。

修改点：

- 在需要确定可用论文时：调用 `list_papers(status="ready")` 查询就绪论文
- 在需要检查论文状态时：调用 `get_paper(paper_id)` 获取单篇论文详情
- 在需要处理失败论文时：检查 `status="failed"` 并读取 `error_message`
- 在需要处理重建时：调用 `list_papers_pending_rebuild()` 获取待重建列表

选择原因：

- 复用已建立的论文存储访问层，保持数据一致性
- 避免在 Planner 层引入新的数据库访问逻辑

考虑过的替代方案：

- 让 Planner 直接连接 SQLite：会增加耦合，违背分层设计

### 决策 2：Planner Policy 增加论文状态相关的决策规则

`app/planner_policy.py` 将增加基于论文生命周期状态的决策规则。

修改点：

- 在 catalog_lookup 工具调用前：过滤掉非 `ready` 状态的论文
- 在生成 action plan 时：将论文状态作为依赖条件
- 在识别到 `failed` 论文时：在计划中标记不可用并建议重试
- 在识别到 `rebuild_pending` 论文时：提示用户或触发重建

选择原因：

- 让 Policy 层成为论文状态感知的决策点
- 保持运行时与策略的分离

考虑过的替代方案：

- 在运行时层处理论文状态过滤：会混淆运行时与策略职责

### 决策 3：Planner 的 action plan 支持论文状态依赖声明

action plan 中的步骤可以声明对论文状态的依赖，执行器按依赖顺序执行。

修改点：

- 在 action plan JSON 中增加 `paper_dependencies` 字段
- 声明依赖格式：`{"paper_id": "p1", "required_status": "ready"}`
- 执行器在执行步骤前检查依赖是否满足

选择原因：

- 显式声明依赖使执行流程可预测
- 支持复杂的论文级执行编排

考虑过的替代方案：

- 隐式依赖推断：难以调试和维护

### 决策 4：保持现有 Planner API 契约不变

所有修改必须保持现有 Planner API 契约不变，平滑过渡。

修改点：

- `planner decision` 的输出格式保持不变
- `tool contract` 的注册格式保持不变
- 仅修改内部实现，不改变接口契约

选择原因：

- 降低对上游调用方的影响
- 允许渐进式迁移

考虑过的替代方案：

- 修改 API 契约：会引入破坏性变更

## 风险 / 权衡

- [Planner 层增加数据库查询可能影响性能] → 使用缓存策略减少重复查询；优先使用 `list_papers` 批量查询而非逐条 `get_paper`
- [论文状态查询失败会影响 Planner 决策] → 定义降级策略：如数据库不可用时，可暂时回退到文件产物读取（带警告）
- [新增依赖声明会增加 action plan 复杂度] → 限制依赖声明的复杂度（如最多 3 层依赖）；提供工具验证依赖图

## 迁移计划

1. 修改 `app/planner_runtime.py`，在需要论文状态时调用 `paper_store` 模块
2. 修改 `app/planner_policy.py`，增加基于论文状态的决策规则
3. 更新 catalog_lookup tool 的实现，使其从 SQLite 过滤 `ready` 论文
4. 更新执行器逻辑，使其支持论文状态依赖检查
5. 为 Planner 层增加论文状态查询的单元测试
6. 验证 Planner 核心链路在论文状态感知模式下的稳定性
7. 逐步移除 Planner 层对 `papers.json` 的直接读取

回滚策略：

- 如 Planner 层出现问题，可暂时禁用论文状态感知功能
- 保留现有文件读取逻辑作为降级路径
- 通过配置切换回原有实现

## 开放问题

- Planner 层是否需要缓存论文状态以减少数据库查询？
- 如何处理论文状态在执行过程中变化的情况？
- 是否需要为 Planner 提供批量查询论文状态的专用接口？
