## 新增需求

### 需求:系统必须在 llm-first planner 迁移期保持聊天体验兼容稳定
聊天页在 llm-first planner、shadow mode 与规则回退共存的迁移期，必须继续以标准聊天协议闭合会话，并允许高层 planner / tool / fallback 事件作为增强层存在；禁止因 shadow 对比或 planner source 切换导致用户可见消息链路中断、重复闭合或必须依赖调试字段才能正常使用。

#### 场景:shadow 模式下聊天主体验保持不变
- **当** 后端在 shadow mode 下同时生成 rule planner 与 LLM planner 的决策
- **那么** 聊天页必须仍以单一主回答流展示本轮结果，而不是向普通用户同时展示两条竞争性的 planner 结果

#### 场景:planner source 回退后聊天仍正常闭合
- **当** LLM planner 决策被拒绝并回退到 rule planner 或 legacy 路径
- **那么** 聊天页必须仍能收到受控的标准消息闭合事件，并保持历史会话和输入区可继续使用
