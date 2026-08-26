"""
能源审计报告批量向量化入库脚本

标签层级:
  audit_type: 公共机构 / 公共建筑 / 工业企业
  institution_category: 医疗 / 教育 / 党政机关 / 场馆机构
  specific_type: 医院 / 大学 / 法院 / ...

入库流程:
  1. 扫描目录 → 识别报告
  2. 按文件名规则打标签
  3. python-docx 提取文本
  4. 按"第X章"切分章节
  5. 写入 Qdrant (collection: energy_audit_reports)
"""

import os, sys, re, json
from pathlib import Path
from typing import Dict, List

# ============================================================
# 标签映射（共享模块）
# ============================================================
from tools.energy_audit.institution_classifier import classify_institution


def classify(filename: str) -> dict:
    """根据文件名打标签"""
    cat, spec = classify_institution(filename)
    return {'audit_type': '公共机构', 'institution_category': cat, 'specific_type': spec}


# ============================================================
# 文档切分
# ============================================================

CHAPTER_PATTERN = re.compile(r'第\s*([一二三四五六七八\d]+)\s*章')


def chunk_report(docx_path: str) -> List[dict]:
    """将一份报告按章节切分为多个 chunk"""
    from docx import Document
    doc = Document(docx_path)

    chunks = []
    current_chapter = '封面'
    current_text = []

    for para in doc.paragraphs:
        t = para.text.strip()
        if not t:
            continue

        m = CHAPTER_PATTERN.search(t)
        if m and len(t) < 80:
            # 保存上一章
            if current_text:
                chunks.append({
                    'chapter': current_chapter,
                    'text': '\n'.join(current_text),
                })
            current_chapter = t[:60]
            current_text = [t]
        else:
            current_text.append(t)

    # 最后一章
    if current_text:
        chunks.append({
            'chapter': current_chapter,
            'text': '\n'.join(current_text),
        })

    return chunks


# ============================================================
# Qdrant 入库
# ============================================================

def ingest_to_qdrant(chunks: List[dict], tags: dict, filename: str):
    """将报告 chunks 写入 Qdrant"""
    from qdrant_client import QdrantClient
    from qdrant_client.models import PointStruct, VectorParams, Distance
    from rag.config import qdrant_client_kwargs, reports_collection
    from rag.embedding import embed_query

    client = QdrantClient(**qdrant_client_kwargs())
    collection_name = reports_collection()

    # 确保 collection 存在
    collections = [c.name for c in client.get_collections().collections]
    if collection_name not in collections:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
        )
        resp = openai_client.embeddings.create(
            model="text-embedding-v3",
            input=text,
            dimensions=1024,
        )
        return resp.data[0].embedding

    points = []
    for i, chunk in enumerate(chunks):
        # 生成唯一 ID
        safe_name = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff]', '_', filename)[:40]
        point_id = hash(f"{safe_name}_{i}") % (2**63)

        # 嵌入文本
        text_to_embed = f"{tags['audit_type']} {tags['institution_category']} {tags['specific_type']} {chunk['chapter']} {chunk['text'][:2000]}"
        try:
            vector = embed_query(text_to_embed)
        except Exception:
            vector = [0.0] * 1024  # fallback

        points.append(PointStruct(
            id=point_id,
            vector=vector,
            payload={
                'filename': filename,
                'chapter': chunk['chapter'],
                'text': chunk['text'][:3000],
                'audit_type': tags['audit_type'],
                'institution_category': tags['institution_category'],
                'specific_type': tags['specific_type'],
                'char_count': len(chunk['text']),
            }
        ))

        if (i + 1) % 50 == 0:
            print(f"  ... {i+1}/{len(chunks)} chunks embedded")

    if points:
        client.upsert(collection_name=collection_name, points=points)
        print(f"  ✓ {len(points)} chunks uploaded")

    return len(points)


# ============================================================
# 批量处理
# ============================================================

def main():
    from rag.config import qdrant_grpc_port, qdrant_host, reports_collection
    report_dirs = [
        "E:/工作目录/能源审计/省直能源审计报告0620（word版本）",
        "E:/工作目录/能源审计",
    ]

    total_chunks = 0
    report_count = 0

    for rd in report_dirs:
        if not os.path.isdir(rd):
            continue
        for fname in os.listdir(rd):
            if not fname.endswith('.docx') or fname.startswith('~$') or fname.startswith('能'):
                continue
            full_path = os.path.join(rd, fname)
            if os.path.getsize(full_path) < 10000:  # 跳过空文件
                continue

            tags = classify(fname)
            print(f"\n[{tags['institution_category']}/{tags['specific_type']}] {fname}")

            try:
                chunks = chunk_report(full_path)
                print(f"  {len(chunks)} chapters: {', '.join(c['chapter'] for c in chunks[:5])}...")
                n = ingest_to_qdrant(chunks, tags, fname)
                total_chunks += n
                report_count += 1
            except Exception as e:
                print(f"  ✗ FAILED: {e}")

    print(f"\n{'='*50}")
    print(f"完成: {report_count} 份报告, {total_chunks} 个 chunk 入库")
    print(f"Collection: {reports_collection()} @ {qdrant_host()}:{qdrant_grpc_port()}")


if __name__ == '__main__':
    main()
