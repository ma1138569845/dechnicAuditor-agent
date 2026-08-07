# 向量模型配置指南

本指南配套 `llamaindex_qdrant_qa.py`（DeepSeek LLM + Qwen 向量 + Qdrant）。

## 📋 配置清单

| 配置项 | 状态 | 说明 |
|--------|------|------|
| Qdrant 服务 | ✅ 已就绪 | http://10.10.2.55:6333 |
| energy_audit_reports 集合 | ✅ 197 points, 1024维 | Qwen text-embedding-v3 向量化，可直接查询 |
| DeepSeek API Key | ⚠️ 需配置 | OpenAI 兼容, 仅 LLM |
| DashScope API Key | ⚠️ 需配置 | 阿里云百炼, 用于 Qwen 向量模型 |

---

## 🚀 配置步骤

### 步骤 1: 获取 API Key

- **DeepSeek**: 访问 https://platform.deepseek.com/ 注册, 创建 API Key (sk-xxx)
  - DeepSeek 仅提供 LLM (deepseek-v4-flash / deepseek-v4-pro), **不提供向量模型**

- **DashScope (阿里云百炼)**: 访问 https://bailian.console.aliyun.com/ 开通, 创建 API Key (sk-xxx)
  - 用于 Qwen `text-embedding-v3` 向量模型 (1024 维)

### 步骤 2: 配置环境变量

```bash
# Windows CMD
set DEEPSEEK_API_KEY=sk-你的deepseek-key
set DASHSCOPE_API_KEY=sk-你的dashscope-key

# Windows 永久生效
setx DEEPSEEK_API_KEY "sk-你的deepseek-key"
setx DASHSCOPE_API_KEY "sk-你的dashscope-key"

# Linux / macOS
export DEEPSEEK_API_KEY=sk-你的deepseek-key
export DASHSCOPE_API_KEY=sk-你的dashscope-key
```

可选覆盖项:
```bash
DEEPSEEK_MODEL     默认 deepseek-v4-flash
QWEN_EMBED_MODEL   默认 text-embedding-v3
QWEN_EMBED_DIM     默认 1024 (text-embedding-v3 标准维度, 匹配 energy_audit_reports)
QDRANT_URL         默认 http://10.10.2.55:6333
QDRANT_COLLECTION  默认 energy_audit_reports
```

### 步骤 3: 准备文档

```bash
mkdir docs
# 把 PDF/TXT/Markdown 文档放进 docs/ 目录
```

### 步骤 4: 构建索引并测试

```bash
# 构建索引 (Qwen 向量化 → 写入 Qdrant)
python llamaindex_qdrant_qa.py build

# 单次问答
python llamaindex_qdrant_qa.py query "这些文档的主要内容是什么？"

# 交互式问答
python llamaindex_qdrant_qa.py chat
```

---

## 📐 模型维度对照表

| 模型 | 维度 | 来源 | 是否需 API Key | 匹配 energy_audit_reports |
|------|------|------|---------------|----------------------|
| **text-embedding-v3 (Qwen)** | **1024** | DashScope | 是 (DASHSCOPE) | ✅ **完全匹配** |
| nomic-embed-text | 768 | Ollama 本地 | 否 | ❌ 维度冲突 |
| bge-large-zh-v1.5 | 1024 | Ollama 本地 | 否 | ✅ 匹配 |
| bge-m3 | 1024 | Ollama 本地 | 否 | ✅ 匹配 |
| text-embedding-3-small | 1536 | OpenAI | 是 | ❌ 维度冲突 |

**当前方案**: Qwen `text-embedding-v3` (1024 维) 直接复用 `energy_audit_reports`, 无需新建集合, 不会报 `vector dimension error`。

---

## 🧠 模型分工说明

| 角色 | 模型 | 端点 | 用途 |
|------|------|------|------|
| LLM (生成答案) | DeepSeek deepseek-v4-flash | https://api.deepseek.com | 读取检索到的上下文 + 问题, 生成自然语言答案 |
| 向量 (嵌入) | Qwen text-embedding-v3 | https://dashscope.aliyuncs.com/compatible-mode/v1 | 把文档/问题转成 1024 维向量, 供 Qdrant 检索 |
| 向量库 | Qdrant | http://10.10.2.55:6333 | 存储向量 + payload, 语义检索 |

DeepSeek 和 Qwen 均通过 OpenAI 兼容协议调用, LlamaIndex 的 `OpenAI` / `OpenAIEmbedding` 类直接支持 `api_base` 参数, 无需额外集成包。

---

## ✅ 验证配置

```bash
# 1. 验证 Qdrant 集合维度
curl http://10.10.2.55:6333/collections/energy_audit_reports
# 检查 vectors.config.size 应为 1024

# 2. 验证 DeepSeek API (LLM)
curl https://api.deepseek.com/v1/models -H "Authorization: Bearer $DEEPSEEK_API_KEY"

# 3. 验证 DashScope 向量模型
curl -X POST https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings \
  -H "Authorization: Bearer $DASHSCOPE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"text-embedding-v3","input":"测试向量维度"}'
# 返回的 data[0].embedding 长度应为 1024
```

---

## 🧯 故障排除

**`vector dimension error` / 写入 Qdrant 失败**:
- 确认 `QWEN_EMBED_DIM=1024` 与目标集合维度一致
- 若用新集合, build 时 LlamaIndex 会按 embed 模型维度自动建集合

**DeepSeek 报 401 / invalid api key**:
- 确认 `DEEPSEEK_API_KEY` 已设置, 且用 `https://api.deepseek.com` (不带 /v1)

**DashScope 报错**:
- 确认 `DASHSCOPE_API_KEY` 已开通百炼服务
- `embed_batch_size` 默认 10, 报 429 限流时调低

**Qdrant Python SDK 超时但 curl 正常**:
- httpx HTTP/2 兼容问题, 可尝试 `QdrantClient(url=..., prefer_grpc=True, port=6334)`

**DeepSeek 报 `completions api is only available when using beta api`**:
- 代码已在 `_register_models()` 把 DeepSeek 注入 `CHAT_MODELS`, 强制走 `/chat/completions`。
- 若仍报错, 确认用的是最新 `llamaindex_qdrant_qa.py`。

**Qwen 报 `'text-embedding-v3' is not a valid OpenAIEmbeddingModelType`**:
- 代码已在 `_register_models()` 里 (1) 扩展枚举 + (2) monkeypatch `get_engine` 透传未知模型名。
- **注意** DashScope 兼容端点不接受 `dimensions` 参数 (传了会报 `Required body invalid`),
  `text-embedding-v3` 默认输出 1024 维, 已匹配 `energy_audit_reports`, 无需指定。