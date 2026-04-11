## 上下文

当前仓库已经具备两类基础：

1. `app/ingest.py` 已有 Marker preflight、解析失败 fallback 与可观测字段。
2. 文档已经说明 Marker 是“可选依赖”，但默认配置和安装路径仍让它表现得像主路径。

因此这次变更不是重写解析体系，而是重新定义默认运行模式：

```text
旧模式
marker-first
  -> marker preflight
  -> marker parse
  -> fallback legacy

新模式
legacy-default
  -> 轻量解析默认可用
  -> marker 仅在显式启用时进入
  -> marker 失败后受控降级回轻量解析
```

这里借鉴 `example_projects/LightRAG` 的不是具体库选型，而是它的本地文档处理策略：

- 默认使用轻量解析器
- 增强引擎只在显式配置且可用时启用
- 不同文件类型映射到各自的基础解析器
- 增强失败不阻断导入，只产生结构化降级信号

`LightRAG` 当前支持的本地受理面较宽，至少覆盖：

- 纯文本与标记类：`txt/md/mdx/html/htm/tex/json/xml/yaml/yml/csv/log/conf/ini/properties/sql`
- Office / 复杂文档类：`pdf/docx/pptx/xlsx/rtf/odt/epub`
- 代码类：`c/h/cpp/hpp/py/java/js/ts/swift/go/rb/php/css/scss/less`

对当前仓库而言，不需要一次把所有类型都做到高保真，但设计上必须从一开始支持“多类型统一接入 + 按类型回退”的框架，而不是只为 `pdf/docx` 写特判。

## 目标 / 非目标

**目标：**
- 将 Marker 定义为显式启用的增强解析器。
- 让前端提供 Marker 总开关与当前模式摘要。
- 在后端建立清晰的本地降级矩阵，参考 LightRAG 的“按文件类型回退”思想。
- 让导入结果在前端和 trace 中清楚区分“普通基础解析”与“增强降级完成”。

**非目标：**
- 本次不引入 `docling` 作为新的默认引擎。
- 本次不要求所有文档类型都具备与 Marker 同等级别的结构化增强；对非 PDF 类型，首版以稳定文本抽取和统一错误/状态语义为主。
- 本次不改变 Marker 结构语义、标题门禁和 artifact 管理的既有细节语义。

## 决策

### 决策 1：默认本地文档解析路径改为 legacy-first
系统默认配置必须将 Marker 视为关闭状态。只有当管理员在设置页或配置文件中显式开启后，导入流程才尝试 Marker preflight 与结构化解析。

选择理由：
- 这直接解决个人电脑环境下“能否先跑起来”的问题。
- 符合用户当前诉求，也更接近 LightRAG 的默认轻量处理哲学。

替代方案：
- 保持 `marker_enabled=true`，仅优化错误提示。缺点是安装和运行复杂度仍默认压在用户身上。

### 决策 2：采用“增强解析器 + 基础解析器”两层模型，而不是“单主路 + 异常兜底”
后端必须将文档处理建模为：

- `base parser`: 默认基础解析器
- `enhanced parser`: 可选增强解析器（当前为 Marker）

当 `enhanced parser` 未启用、不可用或执行失败时，系统必须回到 `base parser`，并根据情况输出：

- `base_only`: 从未尝试增强
- `degraded_from_marker`: 已尝试增强但降级完成

选择理由：
- 这种模型比“主路失败后 fallback”更容易被前端、文档和用户理解。
- 更接近 LightRAG 的 `DEFAULT / DOCLING` 语义。

### 决策 3：前端设置页新增 Marker 总开关，位置与 tuning 同级
前端设置页必须提供：

- Marker 总开关
- 当前模式摘要：`基础解析` / `增强解析`
- 开启 Marker 时的资源提示与风险说明

Marker tuning 与 Marker LLM 配置仅在开关开启时作为增强配置暴露，关闭时仍可保留已存值但不生效。

选择理由：
- 让“是否启用 Marker”成为显式产品决策，而不是隐含在底层配置里。
- 避免用户误以为 tuning 页面存在就代表 Marker 必须始终启用。

### 决策 4：后端降级矩阵参考 LightRAG 的“按文件类型选择基础解析器”
本次设计参考 LightRAG 的文件类型分流模式，但按当前仓库能力收敛为统一矩阵：

```text
Text-like
  txt/md/mdx/html/htm/tex/json/xml/yaml/yml/csv/log/conf/ini/properties/sql
    -> UTF-8 text reader / lightweight normalizer

PDF
  base parser      -> legacy PDF parser
  enhanced parser  -> marker

Office
  docx -> python-docx
  pptx -> python-pptx
  xlsx -> openpyxl

Document-like fallback group
  rtf/odt/epub
    -> lightweight text extraction path or explicit unsupported-with-guidance

Code-like
  c/h/cpp/hpp/py/java/js/ts/swift/go/rb/php/css/scss/less
    -> UTF-8 text reader / lightweight normalizer
```

即使首版仍以 PDF 结构化增强为核心，也必须把后端入口、内部命名和错误语义调整为更通用的“多类型 base/enhanced parser”模型，而不是继续把 Marker 写死为唯一前提。

### 决策 5：导入状态必须同时表达“文件类型路由结果”和“增强降级结果”
当系统开始支持多种文档类型后，前端与 trace 不能只展示“marker fallback”这一类语义，还必须区分：

- 该文件走的是哪一类基础解析器
- 是否存在增强解析尝试
- 是否发生增强降级
- 是否因文件类型尚未支持而被受控跳过

选择理由：
- 多类型受理后，单一 `marker -> legacy` 文案不足以解释实际行为。
- 这能避免用户把“文本类文件直走基础解析”误判为“功能退化”。

## 风险 / 权衡

- [默认关闭 Marker 可能让部分高保真解析效果下降] -> 通过前端开关、文档说明和运行态摘要明确“增强模式”入口。
- [现有测试和脚本默认假设 Marker 已开启] -> 需要同步修正 fixtures、断言与默认配置预期。
- [前端可能把 `marker_enabled=false` 误显示为故障] -> 必须把“未启用”建模为正常状态，而不是 `degraded` 或 `error`。
- [多种文件类型一起纳入后复杂度会上升] -> 用统一注册表或路由表管理“扩展名 -> 基础解析器 -> 增强解析器”映射，避免散落 `if/else`。
- [未来扩展到更多文档类型时接口再变更] -> 当前设计先把解析层命名和状态语义抽象出来，给后续扩展留口。

## Migration Plan

1. 调整后端配置默认值与依赖说明，明确 Marker 为可选增强能力。
2. 在设置页新增 Marker 总开关，并让 runtime overview 返回其生效状态。
3. 在 ingest 中引入“按文件类型路由到基础解析器”的统一入口，并将增强解析决策分离为 `base_only` 与 `degraded_from_marker` 两类受控路径。
4. 在导入工作台和状态映射中同步区分“基础解析完成”“增强降级完成”“按类型受控跳过”。
5. 更新启动、导入和运维文档，明确本地默认不依赖 Marker。

## Open Questions

- 已定：`marker-pdf` 继续保留在现有依赖体系与运维文档中，不额外拆分独立依赖文件；产品语义通过默认关闭与可选安装说明体现“软依赖”。
- 已定：前端首版只在设置页暴露 Marker 总开关，不在导入工作台增加快捷切换入口，避免把导入执行与运行态治理混在一起。
- 已定：首版一次补齐文本类、Office 类与 `rtf/odt/epub` 文档类的基础解析/受控跳过路径，不再拆成两阶段推进。
