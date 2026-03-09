# 本地模型安装与接入（Ollama 主路径）

适用目标：在个人 8GB 显存设备上优先本地化 `embedding/rerank/rewrite`。

## 默认模型档位

- `embedding`: `BAAI/bge-small-zh-v1.5`
- `rerank`: `BAAI/bge-reranker-base`
- `rewrite`: `Qwen2.5-3B-Instruct`

降级备选：
- `embedding`: `BAAI/bge-base-zh-v1.5`
- `rewrite`: `Qwen2.5-1.5B-Instruct`

## 1) Ollama 一键准备

```bash
scripts/bootstrap_local_llm_ollama.sh
```

可选自定义：

```bash
EMBED_MODEL=BAAI/bge-base-zh-v1.5 \
REWRITE_MODEL=Qwen2.5-1.5B-Instruct \
scripts/bootstrap_local_llm_ollama.sh
```

## 2) 连通性与健康检查

```bash
scripts/check_local_llm_health.sh
```

脚本会检查：
- 本地模型是否已在 Ollama 注册
- Kernel `/health/deps` 是否可访问并返回结构化状态
- `rewrite` 本地路由是否可完成一次真实 `chat/completions` 调用

## 3) 前端模型设置建议

在 `/settings` 页面设置：
- `embedding/rerank/rewrite`: `provider=ollama`, `api_base=http://127.0.0.1:11434/v1`
- `answer/graph_entity`: 按你的线上 API 或本地策略配置

## 4) 失败诊断

1. Ollama 不可达：`tail -n 200 /tmp/ollama-serve.log`
2. 模型缺失：重跑 `scripts/bootstrap_local_llm_ollama.sh`
3. Kernel 不可达：`curl -sS http://127.0.0.1:8000/health`
4. 配置异常：`cat configs/llm_runtime_config.json`

## 5) 回滚到外部 API（可一键）

```bash
ANSWER_API_BASE=https://api.openai.com/v1 \
ANSWER_API_KEY=sk-xxx \
ANSWER_MODEL=gpt-4.1-mini \
scripts/rollback_to_external_api.sh
```

执行后重启 Kernel，再检查：

```bash
curl -sS http://127.0.0.1:8000/health/deps | python3 -m json.tool
```

## 6) vLLM 可选路径（非首轮必需）

当你需要更高吞吐时，可将本地 OpenAI-compatible 入口切到 vLLM（例如 `http://127.0.0.1:8000/v1`）：

- 在设置页把对应 stage 的 `provider` 设为 `vllm`
- 把 `api_base` 改为你的 vLLM endpoint
- 注意显存占用和并发参数，8GB 设备建议先从小模型和低并发开始

不建议在首轮落地同时引入 Ollama + vLLM 双主路径，以免排障复杂度上升。
