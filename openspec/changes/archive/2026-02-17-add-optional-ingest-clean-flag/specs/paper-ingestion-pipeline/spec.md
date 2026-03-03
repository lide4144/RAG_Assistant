## 新增需求

## 修改需求

### 需求:批量论文摄取命令
系统必须提供命令 `python -m app.ingest --input <dir> --out <dir>`，用于批量处理输入目录中的 PDF 文件并在输出目录写入结果文件。系统还必须支持可选参数 `--clean`（或等效命名）用于在 ingest 成功后触发 chunk 清洗流程。

#### 场景:命令参数有效时执行成功
- **当** 用户执行 `python -m app.ingest --input data/papers --out data/processed`，且输入目录存在可读取的 PDF 文件
- **那么** 系统必须完成批处理并在输出目录生成 `chunks.jsonl` 与 `papers.json`

#### 场景:开启清洗参数
- **当** 用户执行 ingest 命令并显式开启 `--clean`
- **那么** 系统必须在 `chunks.jsonl` 生成后继续生成 `chunks_clean.jsonl`

### 需求:chunk 数据结构
系统必须将解析结果写入 `chunks.jsonl`，且每个 chunk 记录必须包含 `chunk_id`、`paper_id`、`page_start`、`text` 字段。系统还必须支持通过清洗流程输出 `chunks_clean.jsonl` 增强记录，且禁止清洗过程覆盖已生成的 `chunks.jsonl` 与 `papers.json`。

#### 场景:任意 chunk 记录结构校验
- **当** 读取 `chunks.jsonl` 的任意一行并解析为对象
- **那么** 该对象必须包含 `chunk_id`、`paper_id`、`page_start`、`text`，且 `text` 不得为空字符串

#### 场景:联动清洗失败不影响主产物
- **当** ingest 主流程成功且 `--clean` 已开启，但清洗步骤执行失败
- **那么** 系统必须保留 `chunks.jsonl` 与 `papers.json`，并将清洗失败作为附加错误记录而非回滚主产物

## 移除需求
