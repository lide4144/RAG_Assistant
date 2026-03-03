# RAG Visual Inspector（`app/ui.py`）使用说明

## 1. 适用范围
- 文件入口：`app/ui.py`
- 运行时：Streamlit
- 目标：在聊天界面中同时查看回答、引用映射和开发者审查信息（trace / evidence / decision）

## 2. 环境准备
```bash
python3 -m venv venv
source venv/bin/activate
venv/bin/python -m pip install -U pip
venv/bin/python -m pip install -r requirements.txt
```

## 3. 启动方式
在项目根目录执行：
```bash
venv/bin/python -m streamlit run app/ui.py
```

说明：
- 推荐使用上面的模块启动命令，避免环境路径差异。
- 当前 `app/ui.py` 已兼容 `streamlit run app/ui.py`，但统一使用 `venv/bin/python -m streamlit ...` 更稳定。

## 4. 页面结构
- 主区域：对话区（User/Assistant 多轮消息）
- 侧边栏：`Inspector / Dev Panel`

主区域能力：
- 提问并触发一轮 QA
- 展示 Assistant 回答
- 展示引用按钮（如 `[1]`、`[2]`）
- 点击引用后在侧边栏查看对应 citation/evidence 详情

侧边栏能力：
- Query 演变：`原始输入 -> Rewrite -> Calibrated Query`
- `evidence_grouped` 审查：
  - `chunk_id`
  - `score_retrieval`
  - `score_rerank`
  - `source`（`graph_expand` 为高亮标签）
- 当 `decision` 为 `refuse/clarify` 时，高亮展示 `reason` 与 `output_warnings`
- `Raw Trace JSON` 展开查看底层字段

## 5. 会话与清空行为
- 按钮：`开启新对话 / 清空上下文`
- 行为：
  1. 调用 `clear_session(old_session_id)`
  2. 生成新的 `session_id`
  3. 清空本地聊天与 trace 状态
- 清空后首轮问题会做 `history_used_turns` 保护检查：
  - 若非 0，会在 UI 显示告警并附加 `session_reset_history_leak_suspected`

## 6. 常见操作流（建议）
1. 启动 UI 并提一个常规问题，确认问答闭环正常。
2. 提一个容易触发图扩展的问题，确认 Inspector 中可见 `graph_expand`。
3. 点击回答中的 `[n]` 引用按钮，确认侧边栏出现“引用 [n] 详情”。
4. 点击清空按钮后提无关问题，确认无历史污染迹象。

## 7. 常见问题
### Q1: 启动时报 `ModuleNotFoundError: No module named 'app'`
建议：
- 在项目根目录执行命令。
- 优先使用：
  ```bash
  venv/bin/python -m streamlit run app/ui.py
  ```
- 确认虚拟环境已激活且依赖已安装。

### Q2: 点击引用按钮没有出现详情
先检查：
- 回答中是否存在 `[n]` 引用标记。
- `answer_citations` 是否包含对应索引（`n <= len(answer_citations)`）。
- Inspector 的 `Raw Trace JSON` 中是否有 `answer_citations` 与 `evidence_grouped`。

### Q3: 为什么看到“无映射”黄色提示
表示回答中的某个 `[n]` 不能映射到 `answer_citations`，UI 会将其禁用，避免误判为“可追溯成功”。
