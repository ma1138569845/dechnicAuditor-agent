# Hermes RAG 知识库系统配置参考

> 所有 RAG 模块统一在 `rag/` 包下
> 最后更新: 2026-07-23

### 快速配置

```bash
hermes rag
```

交互式引导会把 Qdrant / 模型写入 **`{HERMES_HOME}/config.yaml` 的 `knowledge_base:`**，密钥写入 `.env`。
运行时由 `rag/config.py` 统一读取。`rag/qdrant_config.yaml` 不再作为配置源。

---

## 一、配置方式

### 方式 A：通过 config.yaml（唯一行为配置）

在 `{HERMES_HOME}/config.yaml`（Windows Desktop 一般为 `%LOCALAPPDATA%\hermes\config.yaml`）中：

```yaml
knowledge_base:
  qdrant_host: "10.10.2.55"
  qdrant_port: 6334          # gRPC（Desktop 知识库 / rag/*）
  qdrant_http_port: 6333     # REST（LlamaIndex 等）
  summary_model: "deepseek-v4-flash"
  energy_audit_collection: "knowledge_segment_qwen"
```

> **优先级**：环境变量 → `knowledge_base:` → 遗留 `energy_audit.rag` → 包内 `tools/energy_audit/config.yaml` 兜底 → 本机默认值

### 方式 B：密钥通过 .env

```bash
# {HERMES_HOME}/.env
DASHSCOPE_API_KEY=...
DEEPSEEK_API_KEY=...
```

可选覆盖（运维临时用，日常请写 config.yaml）：`QDRANT_HOST`、`QDRANT_PORT`。

API 密钥不要写在 config.yaml 中。

---

## 二、环境变量配置（完整列表）

### 1.1 核心路径

| 变量 | 默认值                        | 说明 | 推荐值                                          |
|------|-------------------------------|------|-------------------------------------------------|
| `HERMES_KNOWLEDGE_ROOT` | `D:\dcEauWork\knowledge\rag`  | 知识库文档文件存储根目录 | `D:\dcEauWork\knowledge\rag`（已有 20+ 文档）   |
| `HERMES_WIKI_VAULT` | `D:\dcEauWork\knowledge\wiki` | LLM Wiki 导出目录（Obsidian 兼容） | `D:\dcEauWork\knowledge\wiki`（独立于文档目录） |

### 1.2 Qdrant 向量数据库

| 变量 | 默认值 | 说明 | 推荐值 |
|------|--------|------|--------|
| `QDRANT_HOST` | `10.10.2.55` | Qdrant 服务地址 | `10.10.2.55`（内网固定 IP） |
| `QDRANT_PORT` | `6334` | Qdrant gRPC 端口（可同时用 6333 HTTP） | `6334`（gRPC 性能更优） |
| `QDRANT_KNOWLEDGE_COLLECTION` | `energy_audit_reports` | 默认知识库的 Qdrant 集合名 | `energy_audit_reports`（已稳定） |

> Qdrant 同一实例同时暴露 6333（HTTP REST）和 6334（gRPC）端口，代码统一走 6334 gRPC。

### 1.3 Embedding 模型

| 变量 | 默认值 | 说明 | 推荐值 |
|------|--------|------|--------|
| `DASHSCOPE_API_KEY` | — | 阿里通义千问 DashScope API 密钥 | **必填**，`text-embedding-v3` 唯一来源 |

> 当前使用 DashScope `text-embedding-v3`，**1024 维 · COSINE 距离**。嵌入逻辑在 `rag/embedding.py` 中，由 `rag/api/knowledge_base.py` 的 `_get_embedding()` 调用。

### 1.4 LLM 调用（摘要/图谱/Wiki 生成）

| 变量 | 默认值 | 说明 | 推荐值 |
|------|--------|------|--------|
| `DEEPSEEK_API_KEY` | — | DeepSeek API 密钥 | **必填**，优先于 OpenAI |
| `OPENAI_API_KEY` | — | OpenAI API 密钥 | DeepSeek 不可用时回退 |
| `DEEPSEEK_API_BASE` | `https://api.deepseek.com/v1` | DeepSeek API 地址 | `https://api.deepseek.com/v1` |
| `SUMMARY_PROVIDER` | `deepseek` | LLM 提供商标识 | `deepseek` |
| `SUMMARY_MODEL` | `deepseek-v4-flash` | LLM 模型名 | `deepseek-v4-flash`（性价比均衡） |

> 调用链：`Hermes auxiliary client` → 环境变量凭证 → 直接 HTTP 调用。走 Hermes 统一配置中心时可省略上述 API KEY 变量。

### 1.5 各功能模型消耗

| 功能 | 函数 | 模型参数 | 输入长度 | 输出 Token | 温度 |
|------|------|---------|---------|-----------|------|
| 文档摘要 | `_llm_summarize` | SUMMARY_MODEL | 10,000 chars | 500 | 0.3 |
| 图谱抽取 | `_llm_extract_graph` | SUMMARY_MODEL | 6,000 chars | 1,500 | 0.1 |
| 单文档 Wiki | `_llm_generate_wiki` | SUMMARY_MODEL | 8,000 chars | 1,500 | 0.4 |
| 文件夹 Wiki | `_llm_generate_folder_wiki` | SUMMARY_MODEL | 24,000 chars | 2,000 | 0.3 |
| GraphRAG 答案 | `_generate_graphrag_answer` | SUMMARY_MODEL | — | 1,200 | 0.3 |

---

## 二、知识库目录结构

### 2.1 目录设计原则

```
rag/
├── data/                          ← 默认 KB 根目录
│   ├── .knowledge_meta.db         ← SQLite 元数据库（所有 KB 共用）
│   ├── energy_audit_reports/       ← KB1 文档存储
│   ├── energy_quota_standards/     ← KB2 文档存储
│   └── energy_audit_technical_guidelines/  ← KB3 文档存储
├── wiki/
│   └── generated/                 ← LLM 生成的 Wiki 页面 (Obsidian 兼容)
└── qdrant_config.yaml             ← Qdrant + 集合配置
```

### 2.2 当前部署

| 知识库 | 类型 | 根路径                                  | 推荐值                                                                |
|--------|------|-----------------------------------------|-----------------------------------------------------------------------|
| energy_audit_reports | `energy_audit` | `rag/data/energy_audit_reports` | 系统默认，不可删除 |
| energy_quota_standards | `energy_audit` | `rag/data/energy_quota_standards` | 系统默认，不可删除 |
| energy_audit_technical_guidelines | `energy_audit` | `rag/data/energy_audit_technical_guidelines` | 系统默认，不可删除 |

> 3 个 KB 为系统默认创建（`is_system=True`），不可通过 WebUI 删除。用户可通过 WebUI 或 API 创建额外的自定义 KB。

---

## 三、SQLite 元数据库

### 3.1 文件位置

```
rag/data/.knowledge_meta.db
```

所有 KB 共用这一个 SQLite 文件。默认为 WAL 模式，支持并发读。

### 3.2 表结构

| 表 | 核心字段 | 记录数 | 用途 |
|----|---------|--------|------|
| `knowledge_bases` | id, name, kb_type, root_path, qdrant_collection, embedding_model, chunking_config, indexing_strategy | 3 | 知识库定义 |
| `knowledge_folders` | id, kb_id, parent_id, name, path, depth | 7 | 文件夹树 |
| `knowledge_documents` | id, kb_id, folder_id, file_name, file_path, file_hash, parse_status, chunk_count, vector_count | 20 | 文档记录 |
| `knowledge_chunks` | id, doc_id, chunk_index, content, char_count, is_enabled, qdrant_point_id | 289 | 文档分块 |
| `vectorization_jobs` | id, doc_id, status, progress, chunks_total, chunks_done | 17 | 向量化任务 |
| `knowledge_entities` | id, kb_id, doc_id, name, entity_type, description | — | 图谱实体 |
| `knowledge_relationships` | id, kb_id, source_entity_id, target_entity_id, relation_type | — | 图谱关系 |
| `knowledge_wiki_pages` | id, kb_id, folder_id, title, slug, content, status, review_status | 6 | Wiki 页面 |
| `knowledge_curation_jobs` | id, kb_id, job_type, status, input_pages | — | 策展任务 |
| `document_state` | rel_path, status, file_hash | 16 | 遗留状态（旧版兼容） |

---

## 四、Qdrant 集合结构

### 4.1 命名规则

| 集合 | 命名方式 | 示例 |
|------|---------|------|
| 文档块集合 | `{qdrant_collection}` | `energy_audit_reports` |
| 实体集合 | `{qdrant_collection}_entities` | `energy_audit_reports_entities` |
| Wiki 集合 | `{qdrant_collection}_wiki` | `energy_audit_reports_wiki` |

`qdrant_collection` 在创建 KB 时指定：
- 默认库：由 `QDRANT_KNOWLEDGE_COLLECTION` 环境变量决定
- 新建库：`kb_{uuid4_hex}` 或手动指定（如 `energy_quota_standards`）

### 4.2 向量参数

```
维度: 1024
距离算法: COSINE
Embedding 模型: dashscope text-embedding-v3
```

### 4.3 Payload 结构

**文档块集合 `{collection}`**

| 字段 | 类型 | 必填 | 来源 |
|------|------|------|------|
| `filename` | string | ✓ | 文件名 |
| `chapter` | string | ✗ | 解析出的章节名 |
| `text` | string | ✓ | chunk 文本内容 |
| `audit_type` | string | ✗ | 能源审计类型 |
| `institution_category` | string | ✗ | 机构类别 |
| `specific_type` | string | ✗ | 具体类型 |
| `source` | string | ✓ | `"chunk"`（文档块）或 `"summary"`（摘要） |
| `doc_id` | string | ✗ | 摘要模式下的文档 ID |

**实体集合 `{collection}_entities`**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `entity_id` | string | ✓ | SQLite knowledge_entities.id |
| `name` | string | ✓ | 实体名称 |
| `entity_type` | string | ✗ | 实体类型（如"机构"、"人名"） |
| `description` | string | ✗ | 实体描述 |
| `text` | string | ✓ | 嵌入用文本（`{name} {type} {description}`） |
| `doc_id` | string | ✓ | 来源文档 ID |
| `source` | string | ✓ | `"entity"` |

**Wiki 集合 `{collection}_wiki`**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `wiki_id` | string | ✓ | SQLite knowledge_wiki_pages.id |
| `title` | string | ✓ | Wiki 标题 |
| `text` | string | ✓ | `{title}\n\n{content}` |
| `doc_id` | string | ✗ | 来源文档 ID（文件夹 Wiki 时为 null） |
| `source` | string | ✓ | `"wiki"` |

---

## 五、索引策略与分块配置

### 5.1 indexing_strategy（每个 KB 独立设置）

```json
{
  "vector": true,        // RAG 向量索引（默认开启）
  "summary": false,      // 自动摘要（默认关闭，推荐关闭）
  "graph": false,        // 自动图谱构建（默认关闭）
  "wiki": false,         // 自动 Wiki 生成（默认关闭）
  "wiki_curate": false,  // Wiki 生成后自动策展（默认关闭，耗 LLM）
  "wiki_vault": ""       // 自定义 vault 路径，留空=默认 E:/data/wiki
}
```

**推荐配置方案**

| 场景 | vector | summary | graph | wiki | wiki_curate | wiki_vault |
|------|--------|---------|-------|------|-------------|------------|
| 纯 RAG 检索 | true | false | false | false | false | "" |
| RAG + 图谱 | true | false | true | false | false | "" |
| RAG + Wiki | true | false | false | true | false | "" |
| 全功能 | true | false | true | true | false | "E:/data/wiki" |

> `summary` 不推荐开启：摘要会以 `source=summary` 存入主集合，混合在正常 chunk 中干扰检索。

### 5.2 chunking_config

**energy_audit 类型（使用 energy_audit_importer 三级分块）**

```json
{
  "strategy": "three_level",
  "max_chunk_size": 512,
  "overlap": 64
}
```

实际分块由 `rag/energy_audit_importer.py` 的 `extract_pdf_structure()` + `build_chunks()` 控制，按 PDF 文档结构（章节 → 段落 → 句子）三级拆解。

**general 类型（通用段落分块）**

```json
{
  "strategy": "paragraph",
  "max_chunk_size": 512,
  "overlap": 64
}
```

使用 `_chunk_general_document()` 函数：按段落拆分，单段落超过 `max_chunk_size` 时按句号切分，相邻 chunk 间 `overlap` 字符重叠。

**推荐值**

| 参数 | 默认值 | 推荐值 | 说明 |
|------|--------|--------|------|
| `strategy` | `three_level` | `three_level` | 能源审计 PDF 专用 |
| `max_chunk_size` | 512 | **512** | 中文约 200-300 字一段，512 字符合适 |
| `overlap` | 64 | **64** | 保证段落衔接不丢上下文 |

---

## 六、LLM 调用链路

### 6.1 调用层级

```
_call_llm()                        ← 统一入口 (L1390)
  ├── Hermes auxiliary client      ← 优先：统一配置/凭证/回退链
  │   ├── SUMMARY_PROVIDER         ← deepseek
  │   └── SUMMARY_MODEL            ← deepseek-v4-flash
  │
  └── 直接 HTTP 调用 (fallback)     ← Hermes 不可用时
      ├── DEEPSEEK_API_KEY + DEEPSEEK_API_BASE
      └── 或 OPENAI_API_KEY
```

### 6.2 Embedding 调用

```
_get_embedding(texts)              ← 专用入口 (L1523)
  └── OpenAI SDK (DashScope 兼容模式)
      ├── base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
      ├── model: text-embedding-v3
      ├── 维度: 1024
      └── 批大小: 10 条/次
```

### 6.3 各功能 Prompt 摘要

| 功能 | Prompt 风格 | 输出格式 |
|------|------------|---------|
| 摘要 | "请用 3-5 句话总结以下文档的核心内容" | 纯文本 |
| 图谱 | "从以下文本中提取知识图谱实体和关系" | `{"entities": [...], "relationships": [...]}` |
| 单文档 Wiki | "根据以下文本生成一篇维基百科风格的知识库条目，300-800 字" | `{"title": "...", "content": "..."}` |
| 文件夹 Wiki | "以下是一个目录中多篇文档的内容节选，请生成一篇主题性条目，800-1500 字" | `{"title": "...", "content": "..."}` |
| GraphRAG 答案 | "请根据下面的知识图谱信息回答用户问题" | 纯文本 |

---

## 七、配置最佳实践总结

### 部署清单

**方式 A：config.yaml（推荐）**

```yaml
# ~/.hermes/config.yaml
knowledge_base:
  knowledge_root: "E:\\工作目录\\能源审计\\审计报告"
  qdrant_host: "10.10.2.55"
  qdrant_port: "6334"
  qdrant_collection: "energy_audit_reports"
  wiki_vault: "E:/data/wiki"
```

```bash
# 密钥仍通过环境变量设置（不要放 config.yaml）
export DASHSCOPE_API_KEY="sk-xxx"
export DEEPSEEK_API_KEY="sk-xxx"
```

# 3. Qdrant 部署（若未部署）
# docker run -d -p 6333:6333 -p 6334:6334 qdrant/qdrant

# 4. WebUI 启动
# hermes webui --port 8788
```

### 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| 上传 PDF 后向量化失败 | DashScope API Key 未设置 | 检查 `DASHSCOPE_API_KEY` |
| Wiki 生成无响应 | DeepSeek API Key 未设置 | 检查 `DEEPSEEK_API_KEY` |
| 实体/关系 Tab 显示"未启用" | 当前是 default KB | 切换到非默认知识库 |
| SQLite 锁冲突 | WebUI 正在写入 | WAL 模式自动处理，重试即可 |
| 跨文档实体不连通 | 按文档独立构建图谱 | 需实现知识库级合并函数 |
