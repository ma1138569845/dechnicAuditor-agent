"""
长期记忆存储系统
使用 Qdrant gRPC 存储对话历史和学习到的知识
"""

import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    Filter,
    FieldCondition,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from rag.config import qdrant_client_kwargs, qdrant_grpc_port

MEMORY_COLLECTION = "hermes_long_term_memory"
KNOWLEDGE_COLLECTION = "hermes_learned_knowledge"

VECTOR_SIZE = 1024


def _get_client() -> QdrantClient:
    """模块级缓存的 QdrantClient (gRPC)."""
    return QdrantClient(**qdrant_client_kwargs(timeout=60))


class LongTermMemory:
    """长期记忆存储系统"""

    def __init__(self, qdrant_host: str | None = None, qdrant_port: int | None = None):
        if qdrant_host:
            self._client = QdrantClient(
                host=qdrant_host, port=int(qdrant_port or qdrant_grpc_port()), prefer_grpc=True, timeout=60,
                check_compatibility=False,
            )
        else:
            self._client = QdrantClient(**qdrant_client_kwargs(timeout=60))
        self.memory_collection = MEMORY_COLLECTION
        self.knowledge_collection = KNOWLEDGE_COLLECTION

    # ── 集合管理 ──

    def _create_collection(self, collection_name: str) -> None:
        """创建 Qdrant 集合（如不存在）."""
        if self._client.collection_exists(collection_name):
            print(f"集合 {collection_name} 已存在")
            return

        self._client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
        print(f"✅ 创建集合 {collection_name} 成功")

        # 创建 payload 索引
        for field_name, field_type in [
            ("timestamp", PayloadSchemaType.INTEGER),
            ("type", PayloadSchemaType.KEYWORD),
            ("session_id", PayloadSchemaType.KEYWORD),
        ]:
            self._client.create_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                field_schema=field_type,
            )

    def create_collections(self) -> None:
        """创建记忆存储集合"""
        self._create_collection(self.memory_collection)
        self._create_collection(self.knowledge_collection)

    # ── 对话存储 ──

    def store_conversation(
        self,
        session_id: str,
        user_message: str,
        ai_response: str,
        metadata: Optional[Dict] = None,
    ) -> Optional[str]:
        """存储对话历史"""
        point_id = str(uuid.uuid4())
        timestamp = int(datetime.now().timestamp())

        self._client.upsert(
            collection_name=self.memory_collection,
            points=[
                PointStruct(
                    id=point_id,
                    vector=[0.0] * VECTOR_SIZE,  # 占位向量
                    payload={
                        "type": "conversation",
                        "session_id": session_id,
                        "timestamp": timestamp,
                        "user_message": user_message,
                        "ai_response": ai_response,
                        "metadata": metadata or {},
                        "created_at": datetime.now().isoformat(),
                    },
                )
            ],
        )
        print(f"✅ 存储对话成功: {point_id}")
        return point_id

    # ── 知识存储 ──

    def store_knowledge(
        self,
        knowledge_type: str,
        content: str,
        source: str,
        metadata: Optional[Dict] = None,
    ) -> Optional[str]:
        """存储学习到的知识"""
        point_id = str(uuid.uuid4())
        timestamp = int(datetime.now().timestamp())

        self._client.upsert(
            collection_name=self.knowledge_collection,
            points=[
                PointStruct(
                    id=point_id,
                    vector=[0.0] * VECTOR_SIZE,  # 占位向量
                    payload={
                        "type": "knowledge",
                        "knowledge_type": knowledge_type,
                        "content": content,
                        "source": source,
                        "timestamp": timestamp,
                        "metadata": metadata or {},
                        "created_at": datetime.now().isoformat(),
                    },
                )
            ],
        )
        print(f"✅ 存储知识成功: {point_id}")
        return point_id

    # ── 检索 ──

    def search_conversations(
        self, session_id: Optional[str] = None, limit: int = 10
    ) -> List[Dict]:
        """搜索对话历史（按 session_id 过滤 + 时间倒序）."""
        scroll_filter = None
        if session_id:
            scroll_filter = Filter(
                must=[FieldCondition(key="session_id", match=MatchValue(value=session_id))]
            )

        points, _ = self._client.scroll(
            collection_name=self.memory_collection,
            scroll_filter=scroll_filter,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )

        conversations = []
        for p in points:
            payload = p.payload or {}
            conversations.append({
                "id": p.id,
                "session_id": payload.get("session_id"),
                "user_message": payload.get("user_message"),
                "ai_response": payload.get("ai_response"),
                "timestamp": payload.get("timestamp"),
                "created_at": payload.get("created_at"),
            })

        conversations.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        return conversations

    def search_knowledge(
        self,
        knowledge_type: Optional[str] = None,
        keyword: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict]:
        """搜索知识库（按类型过滤 + 关键词过滤 + 时间倒序）."""
        scroll_filter = None
        if knowledge_type:
            scroll_filter = Filter(
                must=[
                    FieldCondition(
                        key="knowledge_type", match=MatchValue(value=knowledge_type)
                    )
                ]
            )

        points, _ = self._client.scroll(
            collection_name=self.knowledge_collection,
            scroll_filter=scroll_filter,
            limit=100,  # fetch more for keyword post-filter
            with_payload=True,
            with_vectors=False,
        )

        knowledge_items = []
        for p in points:
            payload = p.payload or {}
            content = payload.get("content", "")

            # 关键词过滤
            if keyword and keyword.lower() not in content.lower():
                continue

            knowledge_items.append({
                "id": p.id,
                "knowledge_type": payload.get("knowledge_type"),
                "content": content,
                "source": payload.get("source"),
                "timestamp": payload.get("timestamp"),
                "created_at": payload.get("created_at"),
            })

        knowledge_items.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        return knowledge_items[:limit]

    # ── 统计 ──

    def get_memory_stats(self) -> Dict:
        """获取记忆统计信息"""
        mem_info = self._client.get_collection(self.memory_collection)
        know_info = self._client.get_collection(self.knowledge_collection)

        return {
            "conversations": {
                "count": mem_info.points_count,
                "collection": self.memory_collection,
            },
            "knowledge": {
                "count": know_info.points_count,
                "collection": self.knowledge_collection,
            },
        }


def main():
    """主函数 - 测试记忆存储系统"""
    memory = LongTermMemory()

    print("=" * 60)
    print("长期记忆存储系统")
    print("=" * 60)
    print()

    # 创建集合
    print("[1] 创建记忆存储集合...")
    memory.create_collections()
    print()

    # 存储对话示例
    print("[2] 存储对话示例...")
    session_id = "test_session_001"

    memory.store_conversation(
        session_id=session_id,
        user_message="医院的能耗指标是多少？",
        ai_response="根据能耗文档，医院的能耗指标包括...",
        metadata={"topic": "能耗查询", "importance": "high"},
    )

    memory.store_conversation(
        session_id=session_id,
        user_message="如何降低建筑能耗？",
        ai_response="降低建筑能耗的方法包括...",
        metadata={"topic": "节能建议", "importance": "medium"},
    )
    print()

    # 存储知识示例
    print("[3] 存储知识示例...")
    memory.store_knowledge(
        knowledge_type="energy_standard",
        content="《党政机关能源消耗定额标准》(DB37/T 2672-2019) 规定了...",
        source="能耗审计报告",
        metadata={"standard": "DB37/T 2672-2019"},
    )

    memory.store_knowledge(
        knowledge_type="energy_formula",
        content="单位建筑面积非供暖能耗计算公式：Ejrcn = (E - Egn - Ejt) / M",
        source="能耗计算方法",
        metadata={"formula_type": "能耗计算"},
    )
    print()

    # 搜索对话
    print("[4] 搜索对话历史...")
    conversations = memory.search_conversations(session_id=session_id, limit=5)
    for conv in conversations:
        print(f"  - {(conv.get('user_message') or '')[:50]}...")
    print()

    # 搜索知识
    print("[5] 搜索知识库...")
    knowledge = memory.search_knowledge(keyword="能耗", limit=5)
    for k in knowledge:
        print(f"  - [{k.get('knowledge_type')}] {(k.get('content') or '')[:50]}...")
    print()

    # 获取统计信息
    print("[6] 记忆统计信息...")
    stats = memory.get_memory_stats()
    print(f"  对话历史: {stats['conversations']['count']} 条")
    print(f"  知识库: {stats['knowledge']['count']} 条")
    print()


if __name__ == "__main__":
    main()
