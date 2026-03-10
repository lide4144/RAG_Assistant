# 本地模型安装与接入（Ollama 主路径）

适用目标：在个人 8GB 显存设备上优先本地化 `embedding/rewrite`，并保留 `rerank` 的外部 API 或 vLLM 路径。

## 0) 前置依赖

- `ollama` 是系统级可执行程序，不属于 `requirements.txt`
- 运行一键拉模前，必须先在宿主机安装 Ollama，并确认 `ollama --version` 可执行

Linux 常用安装方式：

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama --version
```

如果 `scripts/bootstrap_local_llm_ollama.sh` 提示 `[ERROR] missing command: ollama`，说明当前环境还没有安装这个系统依赖。

## 默认模型档位

- `embedding`: `nomic-embed-text`
- `rewrite`: `qwen2.5:3b`

降级备选：
- `embedding`: `bge-m3`
- `rewrite`: `qwen2.5:1.5b`
- `rerank`: 默认不走 Ollama 主路径，建议继续使用外部 API 或单独切到 vLLM/兼容服务

## 1) Ollama 一键准备

```bash
scripts/bootstrap_local_llm_ollama.sh
```

可选自定义：

```bash
EMBED_MODEL=bge-m3 \
REWRITE_MODEL=qwen2.5:1.5b \
scripts/bootstrap_local_llm_ollama.sh
```

## 2) 连通性与健康检查

```bash
scripts/check_local_llm_health.sh
```

脚本会检查：
- 本地模型是否已在 Ollama 注册
- `embedding` 本地路由是否可返回向量
- Kernel `/health/deps` 是否可访问并返回结构化状态
- `rewrite` 本地路由是否可完成一次真实 `chat/completions` 调用

## 3) 前端模型设置建议

在 `/settings` 页面设置：
- `embedding/rewrite`: `provider=ollama`, `api_base=http://127.0.0.1:11434/v1`
- `rerank`: 建议保留 `siliconflow` 或其他 OpenAI-compatible/vLLM 路径，不作为 Ollama 主路径默认值
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
