## 为什么

当前前端默认把浏览器侧的管理接口与 WebSocket 地址指向 `127.0.0.1` / `localhost`。这在单机本地联调时可用，但一旦部署到远程服务器，浏览器会错误地回连到用户自己的设备，导致聊天连接失败、运行态接口拒绝连接，以及“本地可用、服务器不可用”的部署断层。

现在需要把前端默认地址策略改成面向部署环境的安全默认值，同时保留本地开发通过环境变量显式覆盖的能力，避免继续把仅适用于开发机的回环地址暴露给远程访问场景。

## 变更内容

- 将前端默认 API 请求策略调整为“同域优先”，未显式配置 `NEXT_PUBLIC_KERNEL_BASE_URL` 时，浏览器侧管理接口必须优先走当前站点的相对路径，而不是硬编码 `127.0.0.1:8000`；此策略必须覆盖聊天页、全局壳层与设置页等管理接口消费方。
- 将前端默认 WebSocket 策略调整为“按当前页面来源自动推导”，未显式配置 `NEXT_PUBLIC_GATEWAY_WS_URL` 时，聊天页与知识处理页必须基于 `window.location` 自动生成 `ws://` 或 `wss://` 地址，而不是固定使用 `ws://localhost:8080/ws`。
- 保留显式环境变量优先级，确保本地联调、分端口开发和特殊部署仍可通过 `NEXT_PUBLIC_KERNEL_BASE_URL`、`NEXT_PUBLIC_GATEWAY_WS_URL` 覆盖默认策略；开发启动脚本不得覆盖用户已显式传入的前端端点变量。
- 更新启动与部署文档，明确区分“本地联调地址注入”和“远程部署/反向代理”两种模式，并给出 HTTPS/WSS 场景下的期望行为。

## 功能 (Capabilities)

### 新增功能
- `frontend-deployment-endpoint-resolution`: 定义前端在浏览器侧解析 HTTP 管理接口与 WebSocket 地址的默认策略、协议切换规则和环境变量覆盖优先级。

### 修改功能
- `frontend-chat-focused-experience`: 调整聊天页默认连接策略，确保远程部署时聊天 WebSocket 与运行态请求不再回落到浏览器本机回环地址。
- `frontend-llm-connection-settings`: 调整设置页默认连接策略，确保模型管理接口在远程部署和 HTTPS 代理场景下不再回落到浏览器本机回环地址。
- `frontend-pipeline-ops-dashboard`: 调整知识处理页的默认连接策略，确保任务事件通道在远程部署与 HTTPS 场景下可稳定建立。
- `frontend-saas-shell-navigation`: 调整全局壳层运行态请求的默认寻址行为，使其在未显式配置 Kernel 地址时仍可通过同域策略读取运行态。

## 影响

- 受影响前端：`chat-shell`、`pipeline-shell`、`app-shell`、`settings-shell`、管理接口请求封装与地址解析辅助函数。
- 受影响配置与启动方式：`scripts/dev-up.sh` 的前端环境变量注入优先级、Gateway 内部访问 Kernel 的地址选择，以及部署时的环境变量建议。
- 受影响文档：`docs/startup-guide.md`、可能的多服务开发说明与部署说明。
- 受影响测试：前端端到端或组件测试需要覆盖“未配置地址时的同域默认值”“HTTPS 对应 WSS”“显式环境变量覆盖默认值”。
