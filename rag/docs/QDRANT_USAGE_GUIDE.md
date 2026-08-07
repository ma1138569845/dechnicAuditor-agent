# Qdrant 使用指南

本指南介绍如何在 hermes-agent 中使用 Qdrant 向量数据库，涵盖 RAG 问答系统、长期记忆存储和知识图谱查询。

## 目录

1. [系统概述](#系统概述)
2. [配置说明](#配置说明)
3. [RAG 问答系统](#rag-问答系统)
4. [知识图谱查询](#知识图谱查询)
5. [使用示例](#使用示例)
6. [常见问题](#常见问题)

---

## 系统概述

### 当前 Qdrant 实例信息

- **地址**: `http://10.10.2.55:6334` (gRPC)
- **状态**: ✅ 正常运行

### 知识库与集合映射

每个知识库在 Qdrant 中有 **3 个集合**（主文档 + 实体 + Wiki）：

| 知识库 | 主集合 | 实体集合 | Wiki 集合 |
|--------|--------|----------|-----------|
| 能源审计报告 | `energy_audit_reports` | `energy_audit_reports_entities` | `energy_audit_reports_wiki` |
| 能源定额标准 | `energy_quota_standards` | `energy_quota_standards_entities` | `energy_quota_standards_wiki` |
| 能源审计技术指南 | `energy_audit_technical_guidelines` | `energy_audit_technical_guidelines_entities` | `energy_audit_technical_guidelines_wiki` |

---

## 配置说明

### 快速配置向导

```bash
hermes rag
```

交互式引导完成 Qdrant、Embedding、LLM、存储的初始化配置。

非交互模式（脚本部署）：

```bash
hermes rag --non-interactive \
  --qdrant-host 10.10.2.55 --qdrant-port 6334 \
  --embedding-model dashscope/text-embedding-v3 \
  --dashscope-api-key sk-xxx \
  --llm-model deepseek-v4-flash \
  --deepseek-api-key sk-xxx
```

### 配置文件

配置文件位置: `rag/qdrant_config.yaml`

```yaml
qdrant:
  host: "10.10.2.55"
  port: 6334
  url: "http://10.10.2.55:6334"
  timeout: 60
```

---

## RAG 问答系统

### 功能说明

RAG 系统对 3 个知识库进行语义搜索，检索能耗文档并返回相关上下文。

### 模块位置

所有 RAG 模块统一在 `rag/` 包下：

```
rag/
├── embedding.py              # 共享嵌入模块
├── rag_search.py             # RAG 搜索主逻辑
├── rag_retrieval.py          # RAG 检索管道
├── rag_energy_qa.py          # 能源问答入口
├── energy_audit_search.py    # 能耗文档搜索
└── api/
    └── knowledge_base.py     # 知识库管理 API
```

### 使用方法

#### 1. 关键词搜索

```python
from rag.rag_energy_qa import EnergyRAGSystem

rag = EnergyRAGSystem()
results = rag.search_by_keyword("能耗", limit=5)
results = rag.search_by_multiple_keywords(["能耗", "标准"], limit=10)
```

#### 2. 语义搜索（通过知识库 API）

```python
from rag.api import knowledge_base as kb

# 在指定知识库中搜索
results = kb.search_knowledge_v2("energy_audit_reports", "医院能耗指标", top_k=5)
```

#### 3. 获取文档上下文

```python
context = rag.get_document_context(point_id, context_window=2)
print(context['full_context'])
```

#### 4. 运行测试

```bash
PYTHONIOENCODING=utf-8 python rag/rag_energy_qa.py
```

---

## 长期记忆存储

### 功能说明

长期记忆存储使用 Qdrant 存储对话历史和学习到的知识。

### 模块位置

`rag/memory_storage.py`

### 使用方法

```python
from rag.memory_storage import LongTermMemory

memory = LongTermMemory()
memory.create_collections()  # 首次使用

# 存储对话
memory.store_conversation(
    session_id="session_001",
    user_message="医院的能耗指标是多少？",
    ai_response="根据能耗文档，医院的能耗指标包括...",
    metadata={'topic': '能耗查询', 'importance': 'high'}
)

# 搜索对话历史
conversations = memory.search_conversations(session_id="session_001", limit=10)

# 获取统计信息
stats = memory.get_memory_stats()
```

### 运行测试

```bash
PYTHONIOENCODING=utf-8 python rag/memory_storage.py
```

---

## 知识图谱查询

### 功能说明

知识图谱系统结合 `star_charts` 和 3 个知识库集合，实现跨集合搜索和文档关联。

### 模块位置

```
rag/
├── general_kg.py                     # 通用知识图谱
└── knowledge_graph/
    ├── knowledge_schema.py           # 因果推理数据模型
    ├── energy_kg.py                  # 能源审计因果推理
    └── kg_visualizer.py              # 图谱可视化
```

### 使用方法

```python
from rag.general_kg import KnowledgeGraph

kg = KnowledgeGraph()
info = kg.get_collection_info()

# 跨集合搜索
results = kg.cross_collection_search("能耗", limit_per_collection=5)
```

### 运行测试

```bash
PYTHONIOENCODING=utf-8 python rag/general_kg.py
```

---

## 使用示例

### 示例 1: RAG 问答完整流程

```python
from rag.api import knowledge_base as kb

# 列出所有知识库
bases = kb.list_knowledge_bases()
for b in bases:
    print(f"{b['id']}: {b['name']} [system={b['is_system']}]")

# 在指定知识库中搜索
results = kb.search_knowledge_v2("energy_audit_reports", "医院能耗指标是多少？", top_k=5)

# 获取文档详情
for r in results:
    doc = kb.get_knowledge_document(r['doc_id'])
    print(f"来源: {doc['file_name']}")
```

### 示例 2: 对话记忆管理

```python
from rag.memory_storage import LongTermMemory

memory = LongTermMemory()

memory.store_conversation(
    session_id="session_001",
    user_message="如何降低建筑能耗？",
    ai_response="降低建筑能耗的方法包括...",
    metadata={'topic': '节能建议'}
)

history = memory.search_conversations(session_id="session_001")
```

### 示例 3: 知识图谱查询

```python
from rag.general_kg import KnowledgeGraph

kg = KnowledgeGraph()
results = kg.cross_collection_search("能耗标准")

# 分析各集合结果
for col_name, col_data in results.items():
    if col_name != 'total_results':
        print(f"{col_name}: {col_data['count']} 条")
```

---

## 常见问题

### 1. 如何初始化/重新配置？

运行配置向导：

```bash
hermes rag
```

这会自动完成：Qdrant 连接配置、Embedding/LLM 模型配置、本地目录创建、SQLite 表初始化、Qdrant 集合创建。

### 2. 如何使用嵌入模型进行语义搜索？

```python
from rag.embedding import embed_query
from qdrant_client import QdrantClient

query_vector = embed_query("医院能耗指标")
client = QdrantClient(host="10.10.2.55", port=6334)
results = client.search(
    collection_name="energy_audit_reports",
    query_vector=query_vector,
    limit=5
)
```

### 3. 如何向知识库添加新文档？

通过 WebUI 知识库面板上传，或调用 API：

```python
from rag.api import knowledge_base as kb

# 上传文件到指定知识库
doc = kb.upload_knowledge_file_v2(
    kb_id="energy_audit_reports",
    folder_id=None,
    raw_body=file_bytes,
    content_type="application/pdf"
)

# 启动向量化
kb.start_vectorization_v2(doc['id'])
```

### 4. 如何备份和恢复数据？

```bash
# 备份集合快照
curl -X POST "http://10.10.2.55:6334/collections/energy_audit_reports/snapshots"
curl -O "http://10.10.2.55:6334/collections/energy_audit_reports/snapshots/{snapshot_name}"

# 恢复
curl -X PUT "http://10.10.2.55:6334/collections/energy_audit_reports/snapshots/{snapshot_name}"
```

### 5. 检查服务状态

```bash
curl "http://10.10.2.55:6334/"
curl "http://10.10.2.55:6334/collections"
curl "http://10.10.2.55:6334/cluster"
```

---

## 相关资源

- [Qdrant 官方文档](https://qdrant.tech/documentation/)
- [Qdrant Python 客户端](https://github.com/qdrant/qdrant-client)
- [hermes-agent 项目](https://github.com/hermes-agent/hermes-agent)

## 更新日志

- **2026-07-23**: 更新至 rag/ 包结构；3 个默认知识库 + 每 KB 3 集合（主文档/实体/Wiki）；新增 `hermes rag` 配置向导
- **2026-06-24**: 初始版本
