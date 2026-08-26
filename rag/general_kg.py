"""
知识图谱查询系统
结合 star_charts 和 knowledge_segment 集合
使用 Qdrant gRPC 接口
"""

import os
from typing import Dict, List, Optional, Set

from qdrant_client import QdrantClient

from rag.config import energy_audit_collection, qdrant_client_kwargs, qdrant_grpc_port

STAR_CHARTS_COLLECTION = "star_charts"
KNOWLEDGE_SEGMENT_COLLECTION = energy_audit_collection()


def _scroll_all(
    client: QdrantClient, collection_name: str, batch_size: int = 100
) -> List:
    """Scroll all points from a collection."""
    all_points = []
    offset = None
    while True:
        points, next_offset = client.scroll(
            collection_name=collection_name,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        all_points.extend(points)
        if next_offset is None or not points:
            break
        offset = next_offset
    return all_points


class KnowledgeGraph:
    """知识图谱查询系统"""

    def __init__(self, qdrant_host: str | None = None, qdrant_port: int | None = None):
        if qdrant_host:
            self._client = QdrantClient(
                host=qdrant_host, port=int(qdrant_port or qdrant_grpc_port()), prefer_grpc=True, timeout=60,
                check_compatibility=False,
            )
        else:
            self._client = QdrantClient(**qdrant_client_kwargs(timeout=60))
        self.star_charts_collection = STAR_CHARTS_COLLECTION
        self.knowledge_segment_collection = KNOWLEDGE_SEGMENT_COLLECTION

    def get_collection_info(self) -> Dict:
        """获取集合信息"""
        star_info = self._client.get_collection(self.star_charts_collection)
        knowledge_info = self._client.get_collection(self.knowledge_segment_collection)

        return {
            "star_charts": {
                "name": self.star_charts_collection,
                "points_count": star_info.points_count,
                "vector_size": star_info.config.params.vectors.size,
                "distance": star_info.config.params.vectors.distance,
            },
            "knowledge_segment": {
                "name": self.knowledge_segment_collection,
                "points_count": knowledge_info.points_count,
                "vector_size": knowledge_info.config.params.vectors.size,
                "distance": knowledge_info.config.params.vectors.distance,
            },
        }

    def search_star_charts(
        self, keyword: Optional[str] = None, limit: int = 10
    ) -> List[Dict]:
        """搜索 star_charts 集合（关键词过滤）"""
        points, _ = self._client.scroll(
            collection_name=self.star_charts_collection,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )

        charts = []
        for p in points:
            payload = p.payload or {}
            if keyword:
                payload_str = str(payload).lower()
                if keyword.lower() not in payload_str:
                    continue
            charts.append({"id": p.id, "payload": payload})

        return charts[:limit]

    def search_knowledge_segment(
        self, keyword: Optional[str] = None, limit: int = 10
    ) -> List[Dict]:
        """搜索 knowledge_segment 集合（关键词过滤）"""
        all_points = _scroll_all(self._client, self.knowledge_segment_collection)

        knowledge_items = []
        for p in all_points:
            payload = p.payload or {}
            content = payload.get("doc_content", "")

            if keyword and keyword.lower() not in content.lower():
                continue

            knowledge_items.append({
                "id": p.id,
                "content": content[:200] + "..." if len(content) > 200 else content,
                "full_content": content,
                "document_id": payload.get("documentId"),
                "segment_id": payload.get("segmentId"),
                "chunk_index": payload.get("chunk_index"),
                "total_chunks": payload.get("total_chunks"),
            })

        return knowledge_items[:limit]

    def cross_collection_search(
        self, keyword: str, limit_per_collection: int = 5
    ) -> Dict:
        """跨集合搜索：同时搜索 star_charts 和 knowledge_segment"""
        star_results = self.search_star_charts(keyword, limit_per_collection)
        knowledge_results = self.search_knowledge_segment(keyword, limit_per_collection)

        return {
            "keyword": keyword,
            "star_charts": {"count": len(star_results), "results": star_results},
            "knowledge_segment": {
                "count": len(knowledge_results),
                "results": knowledge_results,
            },
            "total_results": len(star_results) + len(knowledge_results),
        }

    def find_related_documents(self, document_id: str) -> Dict:
        """根据 document_id 查找同一文档的所有 chunks"""
        all_points = _scroll_all(self._client, self.knowledge_segment_collection)

        doc_chunks = []
        for p in all_points:
            payload = p.payload or {}
            if payload.get("documentId") == document_id:
                doc_chunks.append({
                    "id": p.id,
                    "chunk_index": payload.get("chunk_index"),
                    "content": payload.get("doc_content", ""),
                    "total_chunks": payload.get("total_chunks"),
                })

        doc_chunks.sort(key=lambda x: x.get("chunk_index", 0))

        return {
            "document_id": document_id,
            "chunks_count": len(doc_chunks),
            "chunks": doc_chunks,
        }

    def build_knowledge_map(self) -> Dict:
        """构建知识图谱：分析文档之间的关联关系"""
        all_points = _scroll_all(self._client, self.knowledge_segment_collection)

        documents: Dict[str, dict] = {}
        knowledge_types: Dict[str, List[str]] = {}

        for p in all_points:
            payload = p.payload or {}
            doc_id = payload.get("documentId")
            content = payload.get("doc_content", "")

            if doc_id not in documents:
                documents[doc_id] = {
                    "document_id": doc_id,
                    "chunks": [],
                    "knowledge_id": payload.get("knowledgeId"),
                    "parent_document_id": payload.get("parent_document_id"),
                }

            documents[doc_id]["chunks"].append({
                "chunk_index": payload.get("chunk_index"),
                "content": content[:100] + "..." if len(content) > 100 else content,
            })

            content_lower = content.lower()
            if "能耗" in content_lower or "energy" in content_lower:
                knowledge_types.setdefault("energy", []).append(doc_id)
            if "标准" in content_lower or "standard" in content_lower:
                knowledge_types.setdefault("standards", []).append(doc_id)
            if "计算" in content_lower or "formula" in content_lower:
                knowledge_types.setdefault("formulas", []).append(doc_id)
            if "建筑" in content_lower or "building" in content_lower:
                knowledge_types.setdefault("buildings", []).append(doc_id)

        return {
            "total_documents": len(documents),
            "total_chunks": len(all_points),
            "documents": documents,
            "knowledge_types": knowledge_types,
        }

    def get_document_summary(self, document_id: str) -> Dict:
        """获取文档摘要"""
        doc_info = self.find_related_documents(document_id)

        if not doc_info["chunks"]:
            return {"error": "文档不存在"}

        chunks = doc_info["chunks"]
        first_chunk = chunks[0]["content"] if chunks else ""
        last_chunk = chunks[-1]["content"] if chunks else ""
        full_content = "\n".join([c["content"] for c in chunks])

        return {
            "document_id": document_id,
            "chunks_count": doc_info["chunks_count"],
            "first_chunk": first_chunk[:200],
            "last_chunk": last_chunk[:200],
            "full_content_length": len(full_content),
            "summary": f"文档包含 {doc_info['chunks_count']} 个分段，总计 {len(full_content)} 字符",
        }


def main():
    """主函数 - 测试知识图谱系统"""
    kg = KnowledgeGraph()

    print("=" * 60)
    print("知识图谱查询系统")
    print("=" * 60)
    print()

    # 获取集合信息
    print("[1] 集合信息:")
    info = kg.get_collection_info()
    for name, details in info.items():
        print(f"  {name}:")
        print(f"    数据点数: {details['points_count']}")
        print(f"    向量维度: {details['vector_size']}")
        print(f"    距离算法: {details['distance']}")
    print()

    # 跨集合搜索
    print("[2] 跨集合搜索 (关键词: '能耗'):")
    results = kg.cross_collection_search("能耗", limit_per_collection=3)
    print(f"  star_charts 结果: {results['star_charts']['count']} 条")
    print(f"  knowledge_segment 结果: {results['knowledge_segment']['count']} 条")
    print(f"  总计: {results['total_results']} 条")
    print()

    # 搜索 star_charts
    print("[3] star_charts 集合内容:")
    charts = kg.search_star_charts(limit=3)
    for chart in charts:
        payload = chart["payload"]
        print(f"  - ID: {chart['id']}")
        if payload:
            print(f"    Keys: {list(payload.keys())}")
    print()

    # 构建知识图谱
    print("[4] 构建知识图谱:")
    knowledge_map = kg.build_knowledge_map()
    print(f"  文档总数: {knowledge_map['total_documents']}")
    print(f"  分段总数: {knowledge_map['total_chunks']}")
    print("  知识类型:")
    for ktype, doc_ids in knowledge_map["knowledge_types"].items():
        print(f"    {ktype}: {len(doc_ids)} 个文档")
    print()

    # 文档摘要示例
    print("[5] 文档摘要示例:")
    if knowledge_map["documents"]:
        first_doc_id = list(knowledge_map["documents"].keys())[0]
        summary = kg.get_document_summary(first_doc_id)
        print(f"  文档ID: {summary.get('document_id', 'N/A')}")
        print(f"  分段数: {summary.get('chunks_count', 0)}")
        print(f"  摘要: {summary.get('summary', 'N/A')}")
    print()


if __name__ == "__main__":
    main()
