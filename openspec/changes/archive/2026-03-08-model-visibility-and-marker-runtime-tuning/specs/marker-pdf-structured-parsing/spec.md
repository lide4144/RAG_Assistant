## 新增需求
<!-- 无 -->

## 修改需求

### 需求:本地 Marker 解析能力
系统必须支持通过运行时配置控制 Surya/Marker 的显存敏感参数，至少包括 `RECOGNITION_BATCH_SIZE`、`DETECTOR_BATCH_SIZE`、`LAYOUT_BATCH_SIZE`、`OCR_ERROR_BATCH_SIZE`、`TABLE_REC_BATCH_SIZE` 与 `MODEL_DTYPE`。系统必须在参数缺失或非法时回退到默认安全值。

#### 场景:8GB 安全档位生效
- **当** 管理员选择 8GB 安全档位（低并行 + `float16`）
- **那么** 系统必须按该档位运行 Marker 解析并在运行报告中可追踪

#### 场景:非法参数自动回退
- **当** 运行时配置提供非法批大小或不支持的 dtype
- **那么** 系统必须记录告警并回退到默认安全值，不得中断整批导入

### 需求:解析可观测性字段
系统必须在 ingest 报告中记录 Marker tuning 的生效值与来源（默认值/运行时配置/环境变量覆盖），用于定位显存瓶颈与性能退化原因。

#### 场景:运行后审计生效参数
- **当** 导入任务结束并生成报告
- **那么** 报告必须包含 tuning 生效参数与 `effective_source` 信息

## 移除需求
<!-- 无 -->
