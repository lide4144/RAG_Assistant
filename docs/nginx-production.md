# Nginx 生产部署指南

本项目推荐在生产环境通过单域名 Nginx 反向代理暴露服务，而不是让浏览器直接访问 `3000`、`8000`、`8080` 多端口。

## 目标拓扑

- 浏览器只访问 `https://your-domain.com`
- Nginx 转发：
  - `/` -> `127.0.0.1:3000`（Next 前端）
  - `/api/admin/*` -> `127.0.0.1:8000`（FastAPI Kernel）
  - `/api/library/*` -> `127.0.0.1:8000`
  - `/api/tasks/*` -> `127.0.0.1:8000`
  - `/ws` -> `127.0.0.1:8080/ws`（Gateway WebSocket）

## 1. 启动内部服务

内部服务推荐只监听服务器本机地址：

```bash
cd /home/programer/RAG_GPTV1.0
KERNEL_HOST=127.0.0.1 \
GATEWAY_HOST=127.0.0.1 \
FRONTEND_PORT=3000 \
scripts/dev-up.sh
```

说明：
- 生产模式下不要给浏览器暴露 `NEXT_PUBLIC_KERNEL_BASE_URL`
- 生产模式下通常也不需要设置 `NEXT_PUBLIC_GATEWAY_WS_URL`
- 前端会优先通过同域 `/api/*` 和 `/ws` 访问后端，由 Nginx 负责转发

如果你不用 `scripts/dev-up.sh`，也可以分别以等价方式启动三项服务，只要内部监听关系保持一致即可。

## 2. 安装 Nginx 配置

项目提供了可直接改造的模板：

- [deploy/nginx/rag-gpt.conf](/home/programer/RAG_GPTV1.0/deploy/nginx/rag-gpt.conf)

使用前请替换：
- `your-domain.com`
- `ssl_certificate`
- `ssl_certificate_key`

安装示例：

```bash
sudo cp deploy/nginx/rag-gpt.conf /etc/nginx/conf.d/rag-gpt.conf
sudo nginx -t
sudo systemctl reload nginx
```

## 3. 环境变量约定

生产环境推荐：

- 不设置 `NEXT_PUBLIC_KERNEL_BASE_URL`
- 不设置 `NEXT_PUBLIC_GATEWAY_WS_URL`
- 让浏览器默认走同域相对路径

只在以下情况才显式覆盖：
- 前端与 Nginx 不在同一域
- 你需要临时调试某个外部 API / Gateway 地址

## 4. 最小验证步骤

### 页面访问

打开：

```text
https://your-domain.com/chat
https://your-domain.com/pipeline
https://your-domain.com/settings
```

预期：
- 页面正常打开
- 浏览器 Network 面板中 API 请求指向当前域名下的 `/api/...`
- WebSocket 连接指向 `wss://your-domain.com/ws`

### HTTP 接口

在服务器上执行：

```bash
curl -I http://127.0.0.1:3000/chat
curl http://127.0.0.1:8000/api/admin/runtime-overview
curl http://127.0.0.1:8080/health
```

对外验证：

```bash
curl -I https://your-domain.com/chat
curl https://your-domain.com/api/admin/runtime-overview
```

### WebSocket

聊天页打开后：
- 浏览器控制台不应再出现 `ws://` from `https://` 的 mixed-content 报错
- 若连接失败，优先检查 Nginx 是否包含 `Upgrade` 和 `Connection` 头转发

## 5. 常见故障排查

### 症状：浏览器出现 CORS 到 `8000` 的报错

- 可能原因：设置了 `NEXT_PUBLIC_KERNEL_BASE_URL`，导致浏览器直接跨域请求 Kernel
- 检查步骤：查看前端请求是否命中了 `https://<kernel-host>:8000/...`
- 修复建议：移除 `NEXT_PUBLIC_KERNEL_BASE_URL`，改为同域 `/api/*` + Nginx 转发

### 症状：HTTPS 页面下 WebSocket 无法连接

- 可能原因：仍在使用 `ws://`，或 Nginx 未透传升级头
- 检查步骤：查看浏览器 Network 是否请求 `wss://your-domain.com/ws`
- 修复建议：确认页面为 HTTPS 时未显式配置 `ws://...`，并检查 Nginx `/ws` 配置

### 症状：页面能打开，但聊天/流水线任务显示未连接

- 可能原因：Gateway 未启动，或 `/ws` 被错误代理到前端
- 检查步骤：
  - `curl http://127.0.0.1:8080/health`
  - 检查 Nginx `/ws` 是否转发到 `127.0.0.1:8080/ws`
- 修复建议：修复 Gateway 进程或反代配置后重试

### 症状：`/api/admin/*` 返回 HTML

- 可能原因：Nginx 把 `/api/admin/*` 错误转发到了前端
- 检查步骤：`curl -i https://your-domain.com/api/admin/runtime-overview`
- 修复建议：确认 `/api/admin/`、`/api/library/`、`/api/tasks/` 都指向 Kernel
