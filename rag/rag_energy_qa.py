"""
RAG 问答系统 - 能耗文档检索
使用 knowledge_segment 集合进行语义搜索（Qdrant gRPC）
"""

import os
from typing import Dict, List

from qdrant_client import QdrantClient

from rag.config import energy_audit_collection, qdrant_client_kwargs, qdrant_grpc_port, qdrant_host

COLLECTION_NAME = energy_audit_collection()


def _scroll_all(client: QdrantClient, collection_name: str) -> List:
    """Scroll all points from a collection."""
    all_points = []
    offset = None
    while True:
        points, next_offset = client.scroll(
            collection_name=collection_name,
            limit=100,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        all_points.extend(points)
        if next_offset is None or not points:
            break
        offset = next_offset
    return all_points


class EnergyRAGSystem:
    """能耗文档 RAG 问答系统"""

    def __init__(self, qdrant_host: str | None = None, qdrant_port: int | None = None):
        if qdrant_host:
            self._client = QdrantClient(
                host=qdrant_host, port=int(qdrant_port or qdrant_grpc_port()), prefer_grpc=True, timeout=60,
                check_compatibility=False,
            )
        else:
            self._client = QdrantClient(**qdrant_client_kwargs(timeout=60))
        self.collection_name = COLLECTION_NAME

    def search_by_keyword(self, keyword: str, limit: int = 5) -> List[Dict]:
        """关键词搜索（无需嵌入模型），遍历所有数据点查找包含关键词的文档"""
        all_points = _scroll_all(self._client, self.collection_name)

        matched_points = []
        for p in all_points:
            payload = p.payload or {}
            content = payload.get("doc_content", "")
            if keyword.lower() in content.lower():
                matched_points.append({
                    "id": p.id,
                    "content": content,
                    "document_id": payload.get("documentId", ""),
                    "segment_id": payload.get("segmentId", ""),
                    "chunk_index": payload.get("chunk_index", 0),
                    "total_chunks": payload.get("total_chunks", 0),
                })

        return matched_points[:limit]

    def search_by_multiple_keywords(
        self, keywords: List[str], limit: int = 10
    ) -> List[Dict]:
        """多关键词搜索，支持 OR 逻辑，按匹配数量排序"""
        all_points = _scroll_all(self._client, self.collection_name)

        matched_points = []
        for p in all_points:
            payload = p.payload or {}
            content = payload.get("doc_content", "").lower()

            matched_keywords = [kw for kw in keywords if kw.lower() in content]
            if matched_keywords:
                matched_points.append({
                    "id": p.id,
                    "content": payload.get("doc_content", ""),
                    "document_id": payload.get("documentId", ""),
                    "segment_id": payload.get("segmentId", ""),
                    "chunk_index": payload.get("chunk_index", 0),
                    "total_chunks": payload.get("total_chunks", 0),
                    "matched_keywords": matched_keywords,
                    "match_count": len(matched_keywords),
                })

        matched_points.sort(key=lambda x: x["match_count"], reverse=True)
        return matched_points[:limit]

    def get_document_context(self, point_id: str, context_window: int = 2) -> Dict:
        """获取文档上下文：根据 chunk_index 获取前后相邻的 chunks"""
        # 获取目标点
        records = self._client.retrieve(
            collection_name=self.collection_name,
            ids=[point_id],
            with_payload=True,
            with_vectors=False,
        )
        if not records:
            return {"error": "无法获取文档信息"}

        record = records[0]
        payload = record.payload or {}
        doc_id = payload.get("documentId")
        chunk_index = payload.get("chunk_index")
        total_chunks = payload.get("total_chunks")

        if not doc_id or chunk_index is None:
            return {"error": "无法获取文档信息"}

        # 获取同一文档的所有 chunks
        all_points = _scroll_all(self._client, self.collection_name)

        doc_chunks = []
        for p in all_points:
            p_payload = p.payload or {}
            if p_payload.get("documentId") == doc_id:
                doc_chunks.append({
                    "id": p.id,
                    "chunk_index": p_payload.get("chunk_index"),
                    "content": p_payload.get("doc_content", ""),
                })

        doc_chunks.sort(key=lambda x: x.get("chunk_index", 0))

        # 获取上下文窗口内的 chunks
        start_idx = max(0, chunk_index - context_window)
        end_idx = min(len(doc_chunks), chunk_index + context_window + 1)

        context_chunks = doc_chunks[start_idx:end_idx]

        return {
            "document_id": doc_id,
            "target_chunk_index": chunk_index,
            "total_chunks": total_chunks,
            "context_chunks": context_chunks,
            "full_context": "\n\n".join([c["content"] for c in context_chunks]),
        }

    def answer_question(self, question: str) -> Dict:
        """回答问题：提取关键词 → 搜索文档 → 构建上下文"""
        energy_keywords = [
            "能耗", "energy", "电力", "电量", "功率", "power",
            "节能", "kwh", "千瓦", "用电", "电耗", "综合能耗",
            "人均能耗", "建筑面积", "定额", "标准", "指标",
        ]

        question_keywords = [kw for kw in energy_keywords if kw in question.lower()]
        if not question_keywords:
            question_keywords = [question]

        results = self.search_by_multiple_keywords(question_keywords, limit=5)

        contexts = []
        for result in results:
            context = self.get_document_context(result["id"], context_window=1)
            if "error" not in context:
                contexts.append(context["full_context"])

        return {
            "question": question,
            "keywords_found": question_keywords,
            "relevant_documents": len(results),
            "contexts": contexts[:3],
            "search_results": results,
        }


def main():
    """主函数 - 测试 RAG 系统"""
    rag = EnergyRAGSystem()

    print("=" * 60)
    print("能耗文档 RAG 问答系统")
    print("=" * 60)
    print()

    test_questions = [
        "医院的能耗指标是多少？",
        "人均综合能耗如何计算？",
        "建筑能耗定额标准是什么？",
        "电力系统运行情况如何？",
    ]

    for question in test_questions:
        print(f"问题: {question}")
        print("-" * 40)

        result = rag.answer_question(question)

        print(f"找到关键词: {result['keywords_found']}")
        print(f"相关文档数: {result['relevant_documents']}")

        if result["contexts"]:
            print("相关上下文:")
            for i, ctx in enumerate(result["contexts"][:2], 1):
                display_ctx = ctx[:200] + "..." if len(ctx) > 200 else ctx
                print(f"  {i}. {display_ctx}")
        print()


if __name__ == "__main__":
    main()
