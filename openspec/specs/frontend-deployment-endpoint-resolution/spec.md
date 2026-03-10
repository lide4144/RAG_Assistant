# frontend-deployment-endpoint-resolution 规范

## 目的
定义浏览器侧管理接口和 WebSocket 在本地开发、远程部署与平台代理环境中的端点解析规则，避免默认回落到本机回环地址。

## 需求
### 需求:系统必须提供浏览器侧端点解析优先级
系统必须为浏览器侧管理接口与 WebSocket 连接提供统一的端点解析优先级。系统必须优先使用显式环境变量；当环境变量未设置时，HTTP 管理接口必须回退到同域相对路径策略，WebSocket 必须回退到基于当前页面来源的自动推导策略；禁止在远程访问默认回退到 `localhost` 或 `127.0.0.1`。

#### 场景:显式环境变量覆盖默认值
- **当** 前端设置了 `NEXT_PUBLIC_KERNEL_BASE_URL` 或 `NEXT_PUBLIC_GATEWAY_WS_URL`
- **那么** 系统必须直接使用显式配置的地址，而不是继续套用同域推导结果

#### 场景:未设置环境变量时采用部署友好默认值
- **当** 前端未设置 `NEXT_PUBLIC_KERNEL_BASE_URL` 且未设置 `NEXT_PUBLIC_GATEWAY_WS_URL`
- **那么** 系统必须将 HTTP 管理接口解析为当前站点下的相对 `/api/admin/*` 路径，并将 WebSocket 解析为当前页面来源对应的 `/ws`

### 需求:系统必须在启动链路中保留显式前端端点变量
系统在开发启动脚本或等效启动链路中，必须保留调用者显式传入的 `NEXT_PUBLIC_KERNEL_BASE_URL` 与 `NEXT_PUBLIC_GATEWAY_WS_URL`，禁止无条件覆盖为本机监听地址；当脚本为本地联调注入默认值时，也必须确保这些默认值只在调用者未显式传值时生效。

#### 场景:外部传入前端管理接口地址
- **当** 调用者在启动前显式设置 `NEXT_PUBLIC_KERNEL_BASE_URL`
- **那么** 启动脚本必须将该值原样传递给前端进程，而不是替换为 `http://127.0.0.1:*`、`http://0.0.0.0:*` 或其他派生地址

#### 场景:外部传入前端 WebSocket 地址
- **当** 调用者在启动前显式设置 `NEXT_PUBLIC_GATEWAY_WS_URL`
- **那么** 启动脚本必须将该值原样传递给前端进程，而不是替换为本机默认 `ws://localhost:*`

### 需求:系统必须按页面协议推导 WebSocket 协议
系统必须根据当前页面协议自动推导 WebSocket 协议：当页面使用 `http` 时必须使用 `ws`，当页面使用 `https` 时必须使用 `wss`；禁止在 HTTPS 页面默认发起 `ws://` 连接。

#### 场景:HTTPS 页面建立 WebSocket
- **当** 用户通过 `https://` 访问前端页面且未显式配置 `NEXT_PUBLIC_GATEWAY_WS_URL`
- **那么** 系统必须使用 `wss://<当前host>/ws` 作为默认连接地址
