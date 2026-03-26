## 新增需求

### 需求:系统必须在 Gateway 事件层区分服务阻断与普通 fallback
Gateway 必须将 planner LLM 基础设施未就绪导致的服务阻断与普通 planner fallback、tool fallback 明确区分。对于服务阻断，Gateway 必须输出稳定的高层阻断语义或阻断状态字段，禁止仅复用普通 `fallback` 事件并让前端自行猜测该状态是否为系统级不可服务。

#### 场景:planner 服务阻断不伪装为普通 fallback
- **当** Kernel 声明 planner LLM 基础设施未就绪并阻断正式聊天入口
- **那么** Gateway 必须向前端输出可区分的服务阻断语义，而不得仅输出模糊的 `fallback` 事件

