## 新增需求
<!-- 如果有新增，请在此处添加完整的需求描述和场景。 -->

## 修改需求

### 需求:系统必须提供全局 SaaS 导航壳层
系统在壳层加载运行态摘要时，必须将管理接口请求稳定路由到 Kernel 服务；当地址未配置或上游返回非 JSON 错误页时，系统必须降级为可读状态提示，禁止抛出前端 JSON 解析异常。未显式配置 `NEXT_PUBLIC_KERNEL_BASE_URL` 时，壳层必须优先使用当前站点下的受控相对路径策略，而不是默认请求 `http://127.0.0.1:8000`。

#### 场景:未显式配置 Kernel 地址时仍可读取运行态
- **当** 前端未设置 `NEXT_PUBLIC_KERNEL_BASE_URL`
- **那么** 系统必须通过当前站点下的受控路径（如相对 `/api/admin/runtime-overview` 或等效 rewrite）请求到 Kernel 的 `/api/admin/runtime-overview`

#### 场景:运行态接口返回 HTML 错误页
- **当** 运行态接口响应 `content-type` 非 `application/json`
- **那么** 系统必须显示“运行态概览加载失败”类可读提示且不出现 `Unexpected token '<'` 解析错误

## 移除需求
<!-- 如果有移除，请在此处添加 -->
