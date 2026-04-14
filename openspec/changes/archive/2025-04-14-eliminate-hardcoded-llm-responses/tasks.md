## 1. 核心硬编码函数删除

### 1.1 删除 `_build_assistant_summary_answer` 函数
- [x] 1.1.1 定位并分析 `app/qa.py` 中 `_build_assistant_summary_answer` 函数（行1477-1538）
- [x] 1.1.2 删除函数定义及相关辅助代码
- [x] 1.1.3 修改调用点（行3832-3842），改为调用标准 LLM 回答流程
- [x] 1.1.4 确保证据上下文正确传递给 LLM
- [x] 1.1.5 运行单元测试验证删除后功能正常

### 1.2 重构 `compose_catalog_answer` 为 LLM 驱动
- [x] 1.2.1 分析 `app/capability_planner.py` 中 `compose_catalog_answer` 函数（行638-690）
- [x] 1.2.2 创建 `format_catalog_context()` 辅助函数格式化目录元数据
- [x] 1.2.3 删除 `compose_catalog_answer` 硬编码输出路径
- [x] 1.2.4 更新所有调用点使用 LLM 驱动流程
- [x] 1.2.5 验证目录查询返回自然语言回答而非格式化列表

### 1.3 删除 `_build_claim_plan` 硬编码逻辑
- [x] 1.3.1 定位 `app/qa.py` 中 `_render_claim_bound_answer` 函数
- [x] 1.3.2 删除 `_render_claim_bound_answer` 硬编码输出函数
- [x] 1.3.3 修改降级路径返回友好错误消息而非硬编码回答
- [x] 1.3.4 删除 `_build_answer` 中死代码（无法到达的硬编码路径）

## 2. 辅助函数清理

### 2.1 清理 `build_answer` 函数
- [x] 2.1.1 分析 `app/generate.py` 中 `build_answer` 函数（行27-31）
- [x] 2.1.2 删除 `app/qa.py` 中对 `build_answer` 的调用和导入
- [x] 2.1.3 统一调用标准 LLM 流程（`_build_answer` 内部）
- [x] 2.1.4 更新导入和依赖关系
- [x] 2.1.5 验证所有调用点正常工作（导入测试通过）

### 2.2 清理其他硬编码路径
- [x] 2.2.1 删除证据不足时的硬编码早期返回
- [x] 2.2.2 修改 `_build_catalog_llm_answer` 中 fallback 为友好错误消息
- [x] 2.2.3 修改 `_catalog_lookup_response` 为简洁提示消息

## 3. 证据上下文格式化

### 3.1 实现目录元数据格式化
- [x] 3.1.1 创建 `format_catalog_context()` 函数（`app/capability_planner.py`）
- [x] 3.1.2 定义上下文格式：标题、作者、年份、状态、摘要

## 修改汇总

### 删除的函数
1. `_build_assistant_summary_answer` - 机械化证据拼接函数
2. `_render_claim_bound_answer` - 硬编码 claim 渲染函数
3. `compose_catalog_answer` - 硬编码目录格式化函数

### 修改的文件
1. `app/qa.py` - 删除多处硬编码回答逻辑
2. `app/capability_planner.py` - 重构目录回答为 LLM 驱动
3. `app/planner_runtime.py` - 修改工具调用响应
4. `app/generate.py` - 保留但未修改（备用）

### 剩余的硬编码（系统级错误消息，保留）
- `clarify_scope` 分支的澄清提示（合理保留）
- LLM 失败时的降级错误消息（友好提示）
- `app/planner_runtime.py` 中的系统错误消息

## 验证
- [x] Python 导入测试通过
- [x] 核心单元测试通过（已修复破坏性变更导致的测试失败）
- [ ] 需要人工测试验证回答质量

## 测试修复记录

### 修复的测试（破坏性变更适配）
1. **test_qa_regressions.py::test_build_answer_does_not_reject_single_paper_match_with_paper_clue**
   - 原测试期望硬编码回答包含论文标题
   - 更新为验证新的降级行为（返回友好错误消息）

2. **test_claim_citation_binding.py::test_binding_falls_back_to_staged_when_claims_not_bound**
   - 原测试期望硬编码 "claim -> citation" 回答
   - 更新为验证新行为（返回空字符串触发 LLM 重新生成）

### 修复的导入错误
- **app/qa.py**: 恢复 `detect_new_topic` 从 `capability_planner` 的导入
  - 在清理导入时不小心删除了此导入
  - 已修复：将 `detect_new_topic` 加回导入列表
