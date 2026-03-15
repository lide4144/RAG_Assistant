## 新增需求
<!-- 无 -->

## 修改需求

### 需求:结构化本地证据 provenance
系统必须允许 citation 结构显式表达本地结构化证据 provenance。对于来自表格块、公式块或其他结构化 Marker block 的本地证据，系统必须在保留现有 `source_type`、`source_id`、`title`、`snippet`、`locator`、`score` 等字段兼容的同时，补充可消费的结构 provenance 字段；系统禁止把这类证据完全伪装成普通正文 chunk citation。

#### 场景:表格证据带结构 provenance
- **当** 回答采用来自表格块的本地证据
- **那么** citation 结构必须能够表明该证据来自表格类结构块，并保留对应定位信息

#### 场景:公式证据带结构 provenance
- **当** 回答采用来自公式块的本地证据
- **那么** citation 结构必须能够表明该证据来自公式类结构块，并保留对应定位信息

### 需求:结构化证据与普通 chunk 兼容输出
系统必须保持普通 chunk citation 的现有兼容字段，同时允许结构化证据附加 provenance 扩展；系统禁止因为引入结构 provenance 而破坏旧消费者对基础 citation 字段的读取。

#### 场景:旧消费者继续读取基础字段
- **当** citation 来自结构化表格块或公式块
- **那么** 旧消费者仍必须能读取基础 citation 字段，而支持结构语义的消费者可以额外读取 provenance 扩展

## 移除需求
<!-- 无 -->
