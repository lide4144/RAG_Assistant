## 上下文

当前项目包含三个独立进程：Next 前端、FastAPI Kernel、Node Gateway。本地开发可以通过 `3000/8000/8080` 多端口访问，但生产环境和托管环境通常要求单域 HTTPS 入口，否则会出现 CORS、`ws/wss` 协议不匹配、端口暴露和平台端口代理不稳定等问题。现有前端已经支持同域相对 `/api/*` 和 `/ws` 的部署友好策略，因此需要补上明确的 Nginx 反向代理方案，并让文档和示例配置与该策略对齐。对于 Cloud Studio 这类平台为每个端口单独分配 HTTPS 链接的环境，还需要在工作空间内部再收敛出一个本机单端口入口。

## 目标 / 非目标

**目标：**
- 提供一个可直接复用的 Nginx 生产反向代理方案，把前端页面、HTTP API 和 WebSocket 收敛到单域入口。
- 提供一个适合 Cloud Studio 的单端口本机 Nginx 入口方案，使平台只需暴露一个应用端口。
- 明确 `/`、`/api/admin/*`、`/api/library/*`、`/api/tasks/*` 与 `/ws` 的代理关系。
- 保持前端默认优先使用同域相对路径，减少生产环境对 `NEXT_PUBLIC_*` 地址变量的依赖。
- 提供部署、验证和回滚指引，使用户可以区分本地 `dev-up.sh` 与生产反代模式。

**非目标：**
- 不引入 Docker、Kubernetes Ingress 或其他新的部署编排系统。
- 不替代现有本地开发脚本；`dev-up.sh` 仍然服务于本地或临时调试。
- 不在本次变更中实现自动 TLS 证书签发；证书获取可以由运维侧或现有平台完成。

## 决策

### Decision: 生产入口采用单域 Nginx 反代

生产部署统一通过一个外部域名暴露服务，Nginx 将浏览器流量分发到内部三个进程：
- `/` 和前端资源 -> Next 前端
- `/api/admin/*`、`/api/library/*`、`/api/tasks/*` -> Kernel
- `/ws` -> Gateway

原因：
- 浏览器只感知一个来源，避免 CORS 和 mixed-content。
- 前端现有同域相对路径设计可以直接复用，不需要浏览器知道 `8000/8080`。
- Nginx 对 WebSocket 透传、TLS 终止和缓存头控制足够成熟。

备选方案：
- 让浏览器直连 `8000/8080`：部署复杂，依赖多端口暴露，跨域风险高。
- 继续依赖平台端口代理：适合临时调试，但不适合作为项目的正式生产方案。

### Decision: Cloud Studio 采用“内部 Nginx 单端口 + 平台应用封装”

对于 Cloud Studio，不要求自定义域名或内层 TLS。工作空间内部额外运行一个监听 `127.0.0.1:<APP_PORT>` 的 Nginx，将 `/`、`/api/*`、`/ws` 分别代理到前端、Kernel、Gateway；平台外层再把这个单端口包装成 HTTPS 链接。

原因：
- Cloud Studio 的每端口独立链接会造成多 origin；单端口入口可以恢复同域模型。
- 平台外层已经处理 HTTPS，因此内部 Nginx 保持 HTTP 即可。
- `next dev` 依赖 `/_next/webpack-hmr` WebSocket，内部 Nginx 也必须透传该路径。

备选方案：
- 继续暴露 `3000/8000/8080` 三个端口：会回到 CORS 和多 origin 问题。

### Decision: 前端生产访问优先走同域相对路径

生产模式下，前端必须优先走相对 `/api/*` 和 `/ws`，由 Nginx 负责内部路由。`NEXT_PUBLIC_KERNEL_BASE_URL` 和 `NEXT_PUBLIC_GATEWAY_WS_URL` 只保留给特殊部署或调试覆盖。

原因：
- 浏览器无需感知内部拓扑，减少环境变量复杂度。
- 与已有部署友好默认值一致。

备选方案：
- 强制要求总是配置公网绝对地址：可行，但对大多数生产部署是额外负担。

### Decision: 文档内同时给出 Nginx 配置模板与部署验证步骤

除了说明代理关系外，部署文档必须给出可复制的 Nginx server 配置，并包含验证步骤，例如 `curl /api/admin/runtime-overview`、浏览器检查 `/ws` 和页面访问。

原因：
- 仅有概念说明不足以帮助用户落地。
- 生产部署失败常见于代理路径或 WebSocket Header 缺失，文档必须覆盖这些检查点。

## 风险 / 权衡

- [需要运维维护 Nginx 配置] -> 提供项目内模板与最小可用说明，降低配置成本。
- [不同部署平台的 TLS/证书策略不同] -> 规范只要求 Nginx 支持 HTTPS/WSS 终止，不绑定具体证书获取方式。
- [本地开发与生产入口存在差异] -> 文档明确区分 `dev-up.sh` 联调模式和 Nginx 生产模式，并保留本地脚本默认行为。
- [WebSocket 代理容易因 Header 不全而失败] -> 配置模板显式包含 `Upgrade`、`Connection`、`Host` 等转发头。

## Migration Plan

1. 新增 Nginx 配置模板或示例文件，定义单域代理规则与 Cloud Studio 单端口规则。
2. 更新前端和文档要求，确保生产访问说明全部使用同域入口。
3. 在部署文档中加入验证命令和常见故障排查。
4. 回滚时可以恢复为原有多端口直连方式，因为内部服务端口和进程拓扑不变。

## Open Questions

- 项目是否需要同时提供 `Nginx` 和 `Caddy` 两套模板，还是先专注 Nginx。
- 生产文档是否应包含 `systemd` 示例，用于管理三个内部进程。
