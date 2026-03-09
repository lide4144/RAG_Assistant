## 新增需求
<!-- 无 -->

## 修改需求

### 需求:前端必须正确回显三路持久化配置
设置页在加载 `/api/admin/llm-config`、`/api/admin/pipeline-config`、`/api/admin/runtime-overview` 时，必须对非 JSON 与错误响应进行受控处理；系统必须先判定响应状态与类型再解析载荷，避免错误页触发 JSON 解析崩溃。

#### 场景:管理接口返回 404 HTML
- **当** 管理接口返回状态码 `4xx/5xx` 且 `content-type` 为 `text/html`
- **那么** 页面必须进入可读错误状态并保持设置表单可继续编辑，不得抛出 `Unexpected token '<'`

#### 场景:管理接口返回结构化错误 JSON
- **当** 管理接口返回错误 JSON（含 `detail` 等字段）
- **那么** 系统必须优先展示可执行错误提示，而不是显示通用解析失败信息

## 移除需求
<!-- 无 -->
