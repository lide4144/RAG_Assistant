## ADDED Requirements

### 需求:会话列表查询接口
系统必须提供API接口支持按时间范围、关键词等条件查询会话列表。

#### 场景:查询最近会话
- **当** 开发者调用 `GET /api/debug/sessions?limit=10`
- **那么** 系统必须返回最近10个会话的基本信息（id、title、created_at、message_count）

#### 场景:按时间范围查询
- **当** 开发者调用 `GET /api/debug/sessions?start_date=2024-01-01&end_date=2024-01-15`
- **那么** 系统必须返回指定日期范围内的所有会话

#### 场景:按关键词搜索会话
- **当** 开发者调用 `GET /api/debug/sessions?query=GraphRAG`
- **那么** 系统必须返回标题或消息内容包含关键词的会话列表

### 需求:会话详情导出接口
系统必须提供API接口导出特定会话的完整数据（消息和turns）。

#### 场景:导出会话消息
- **当** 开发者调用 `GET /api/debug/sessions/{id}/messages`
- **那么** 系统必须返回该会话的所有消息记录，包含完整的metadata

#### 场景:导出会话turns数据
- **当** 开发者调用 `GET /api/debug/sessions/{id}/turns`
- **那么** 系统必须返回该会话的所有turn记录，包含完整的调试上下文

#### 场景:导出完整会话快照
- **当** 开发者调用 `GET /api/debug/sessions/{id}/export`
- **那么** 系统必须返回包含会话、消息和turns的完整JSON快照

### 需求:SQL查询执行接口
系统必须提供安全的SQL查询接口，支持开发者执行只读查询进行调试分析。

#### 场景:执行自定义SQL查询
- **当** 开发者调用 `POST /api/debug/query` 并提交只读SQL语句
- **那么** 系统必须执行该查询并返回结果
- **并且** 系统必须禁止任何写入操作（INSERT/UPDATE/DELETE/DROP等）

#### 场景:查询热门话题统计
- **当** 开发者执行 `SELECT topic, COUNT(*) FROM sessions GROUP BY topic`
- **那么** 系统必须返回各话题的会话数量统计

#### 场景:查询会话平均轮数
- **当** 开发者执行统计查询
- **那么** 系统必须支持聚合函数（COUNT、AVG、SUM等）

### 需求:调试数据可视化支持
系统必须提供API支持前端展示会话调试信息。

#### 场景:获取会话时间线
- **当** 开发者调用 `GET /api/debug/sessions/{id}/timeline`
- **那么** 系统必须返回按时间顺序排列的消息和turns合并视图

#### 场景:获取检索引用详情
- **当** 开发者调用 `GET /api/debug/sessions/{id}/turns/{turn_number}/citations`
- **那么** 系统必须返回该turn引用的所有chunks详细信息
