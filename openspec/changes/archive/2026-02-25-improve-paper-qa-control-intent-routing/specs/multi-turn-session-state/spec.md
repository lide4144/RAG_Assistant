## ADDED Requirements

### 需求:系统必须维护控制意图可复用的主题锚点
系统必须在会话状态中维护最近主题锚点（至少包括最近 `standalone_query` 与关键 `entity_mentions`），供控制意图轮次复用。该锚点必须受轮次距离约束（例如 `style_control_max_turn_distance`），超限时必须触发澄清而非盲目继承。

#### 场景:锚点在距离阈值内可复用
- **当** 当前轮为控制意图且最近主题轮次在阈值内
- **那么** 系统必须返回可用于改写与 topic match 的 `anchor_query`

#### 场景:锚点超限触发澄清
- **当** 当前轮为控制意图且最近主题轮次超过阈值
- **那么** 系统必须要求用户补充主题线索，禁止默认沿用陈旧主题

## MODIFIED Requirements

### 需求:重写输入必须包含历史实体集合
系统必须基于最近 N 轮历史提取 `entities_from_history`（论文名、方法名、指标名等）并传递给 rewrite；该集合必须用于元问题转写的实体保真约束，并必须可用于控制意图场景的主题锚定构建。

#### 场景:历史实体可用于追问补全
- **当** 当前输入缺少明确实体且历史中存在实体
- **那么** rewrite 必须可读取 `entities_from_history` 并用于生成实体完整的 `standalone_query`

#### 场景:控制意图可读取历史实体构造锚点
- **当** 当前输入为 style/format 控制意图
- **那么** 系统必须使用 `entities_from_history` 参与生成 `anchor_query`，并写入 trace 供审查

