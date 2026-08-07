# PDF 文档导入知识图谱指南

本指南介绍如何将 PDF 文档导入到 Qdrant 知识图谱中，以便进行语义搜索和 RAG 问答。

## 📋 目录

1. [快速开始](#快速开始)
2. [安装依赖](#安装依赖)
3. [使用方法](#使用方法)
4. [高级用法](#高级用法)
5. [与 RAG 系统集成](#与-rag-系统集成)
6. [常见问题](#常见问题)

---

## 快速开始

### 最简单的用法

```bash
# 1. 安装依赖
pip install pymupdf pymupdf4llm

# 2. 导入 PDF 文档
python rag/pdf_to_knowledge_graph.py import --pdf your_document.pdf

# 3. 查看已导入的文档
python rag/pdf_to_knowledge_graph.py list

# 4. 搜索文档内容
python rag/pdf_to_knowledge_graph.py search --keyword "能耗"
```

---

## 安装依赖

### 基础依赖（推荐）

```bash
pip install pymupdf pymupdf4llm requests
```

### 高级依赖（OCR 支持）

```bash
# 如果需要处理扫描件或复杂 PDF
pip install marker-pdf
# 注意: marker-pdf 需要约 3-5GB 磁盘空间
```

---

## 使用方法

### 1. 导入 PDF 文档

#### 基础导入

```bash
python rag/pdf_to_knowledge_graph.py import --pdf document.pdf
```

#### 指定提取方法

```bash
# 使用 pymupdf（默认，推荐）
python rag/pdf_to_knowledge_graph.py import --pdf document.pdf --method pymupdf

# 使用 marker-pdf（支持 OCR）
python rag/pdf_to_knowledge_graph.py import --pdf document.pdf --method marker
```

#### 指定页码范围

```bash
# 只导入前 10 页
python rag/pdf_to_knowledge_graph.py import --pdf document.pdf --pages 0-9

# 只导入第 5 页
python rag/pdf_to_knowledge_graph.py import --pdf document.pdf --pages 5-5
```

#### 调整分块大小

```bash
# 默认分块大小为 500 字符
python rag/pdf_to_knowledge_graph.py import --pdf document.pdf --chunk-size 500

# 更大的分块（适合长文档）
python rag/pdf_to_knowledge_graph.py import --pdf document.pdf --chunk-size 1000

# 更小的分块（适合精确搜索）
python rag/pdf_to_knowledge_graph.py import --pdf document.pdf --chunk-size 200
```

### 2. 查看已导入的文档

```bash
python rag/pdf_to_knowledge_graph.py list
```

输出示例：
```
已导入的文档 (3 个):
------------------------------------------------------------
文档 ID: 550e8400-e29b-41d4-a716-446655440000
来源: energy_report.pdf
分块数: 45
上传时间: 2026-06-24T10:30:00
------------------------------------------------------------
文档 ID: 660e8400-e29b-41d4-a716-446655440001
来源: building_standard.pdf
分块数: 32
上传时间: 2026-06-24T11:00:00
------------------------------------------------------------
```

### 3. 搜索文档内容

```bash
# 搜索关键词
python rag/pdf_to_knowledge_graph.py search --keyword "能耗"

# 限制结果数量
python rag/pdf_to_knowledge_graph.py search --keyword "标准" --limit 5
```

输出示例：
```
搜索结果 (3 条):
------------------------------------------------------------
来源: energy_report.pdf, 页码: 5
内容: 单位建筑面积非供暖能耗计算公式：Ejrcn = (E - Egn - Ejt) / M...
------------------------------------------------------------
来源: building_standard.pdf, 页码: 12
内容: 《党政机关能源消耗定额标准》(DB37/T 2672-2019)...
------------------------------------------------------------
```

### 4. 删除文档

```bash
# 先查看文档 ID
python rag/pdf_to_knowledge_graph.py list

# 删除指定文档
python rag/pdf_to_knowledge_graph.py delete --document-id "550e8400-e29b-41d4-a716-446655440000"
```

---

## 高级用法

### 在 Python 代码中使用

```python
from rag.pdf_to_knowledge_graph import PDFToKnowledgeGraph

# 初始化工具
tool = PDFToKnowledgeGraph()

# 导入 PDF
result = tool.process_pdf(
    pdf_path="document.pdf",
    extraction_method="pymupdf",
    chunk_size=500,
    pages="0-10"  # 可选：指定页码范围
)

if result['success']:
    print(f"文档 ID: {result['document_id']}")
    print(f"分块数量: {result['total_chunks']}")
```

### 批量导入多个 PDF

```python
import os
from rag.pdf_to_knowledge_graph import PDFToKnowledgeGraph

tool = PDFToKnowledgeGraph()

# PDF 文件目录
pdf_dir = "./pdfs"

for filename in os.listdir(pdf_dir):
    if filename.endswith('.pdf'):
        pdf_path = os.path.join(pdf_dir, filename)
        print(f"\n处理: {filename}")

        result = tool.process_pdf(pdf_path, chunk_size=500)
        if result['success']:
            print(f"✅ 成功导入: {result['total_chunks']} 个分块")
        else:
            print(f"❌ 导入失败")
```

### 搜索并获取上下文

```python
from rag.pdf_to_knowledge_graph import PDFToKnowledgeGraph

tool = PDFToKnowledgeGraph()

# 搜索关键词
results = tool.search_document("能耗指标", limit=5)

for r in results:
    print(f"来源: {r['source']}, 页码: {r['page_number']}")
    print(f"内容: {r['content']}")
    print()
```

---

## 与 RAG 系统集成

### 完整的 RAG 流程

```python
from rag.pdf_to_knowledge_graph import PDFToKnowledgeGraph
from rag.rag_energy_qa import EnergyRAGSystem

# 1. 导入 PDF 文档
pdf_tool = PDFToKnowledgeGraph()
pdf_tool.process_pdf("energy_report.pdf")

# 2. 使用 RAG 系统搜索
rag = EnergyRAGSystem()
answer = rag.answer_question("医院的能耗指标是多少？")

# 3. 获取相关上下文
contexts = answer['contexts']
print(f"找到 {len(contexts)} 个相关上下文")
```

### 与 LLM 集成生成答案

```python
from rag.pdf_to_knowledge_graph import PDFToKnowledgeGraph
from rag.rag_energy_qa import EnergyRAGSystem

# 初始化
pdf_tool = PDFToKnowledgeGraph()
rag = EnergyRAGSystem()

# 用户问题
question = "如何计算人均能耗？"

# 搜索相关文档
answer = rag.answer_question(question)

# 构建上下文
context = "\n\n".join(answer['contexts'])

# 使用 LLM 生成答案（需要集成 LLM）
prompt = f"""
基于以下上下文回答问题：

上下文：
{context}

问题：{question}

请提供详细的答案：
"""

# 调用 LLM API
# response = call_llm(prompt)
```

---

## 常见问题

### 1. 如何选择提取方法？

**pymupdf（推荐）**：
- ✅ 安装简单（~25MB）
- ✅ 速度快
- ✅ 适合文本型 PDF

**marker-pdf**：
- ✅ 支持 OCR（扫描件）
- ✅ 支持复杂布局
- ❌ 安装大（~3-5GB）
- ❌ 速度较慢

### 2. 分块大小如何选择？

| 分块大小 | 适用场景 | 优点 | 缺点 |
|----------|----------|------|------|
| 200-300 | 精确搜索 | 搜索精度高 | 上下文不完整 |
| 500（默认）| 通用场景 | 平衡精度和上下文 | - |
| 800-1000 | 长文档 | 上下文完整 | 搜索精度降低 |

### 3. 如何处理扫描件 PDF？

```bash
# 安装 marker-pdf
pip install marker-pdf

# 使用 marker 方法导入
python rag/pdf_to_knowledge_graph.py import --pdf scanned.pdf --method marker
```

### 4. 导入后如何验证？

```bash
# 1. 查看文档列表
python rag/pdf_to_knowledge_graph.py list

# 2. 搜索测试
python rag/pdf_to_knowledge_graph.py search --keyword "测试关键词"

# 3. 检查 Qdrant 集合
curl "http://10.10.2.55:6333/collections/energy_audit_reports"
```

### 5. 如何更新已导入的文档？

```bash
# 1. 删除旧文档
python rag/pdf_to_knowledge_graph.py delete --document-id "<旧文档ID>"

# 2. 重新导入
python rag/pdf_to_knowledge_graph.py import --pdf updated_document.pdf
```

### 6. 如何提高搜索质量？

**方案 1：使用嵌入模型**

```python
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient

# 加载嵌入模型
model = SentenceTransformer('BAAI/bge-large-zh-v1.5')

# 生成查询向量
query = "能耗指标"
query_vector = model.encode(query).tolist()

# 语义搜索
client = QdrantClient(url="http://10.10.2.55:6333")
results = client.search(
    collection_name="energy_audit_reports",
    query_vector=query_vector,
    limit=5
)
```

**方案 2：优化分块策略**

```python
# 使用更大的分块，保留更多上下文
python rag/pdf_to_knowledge_graph.py import --pdf document.pdf --chunk-size 800
```

---

## 相关文件

| 文件 | 用途 |
|------|------|
| `pdf_to_knowledge_graph.py` | PDF 导入工具 |
| `rag_energy_qa.py` | RAG 问答系统 |
| `memory_storage.py` | 长期记忆存储 |
| `knowledge_graph.py` | 知识图谱查询 |
| `rag/qdrant_config.yaml` | 配置文件 |

---

## 技术支持

如有问题，请检查：

1. Qdrant 服务是否正常运行
2. 依赖是否正确安装
3. PDF 文件是否存在且可读
4. 网络连接是否正常

---

## 更新日志

- **2026-06-24**: 初始版本
  - 支持 pymupdf 和 marker-pdf 提取
  - 支持分块和上传到 Qdrant
  - 支持搜索和删除文档