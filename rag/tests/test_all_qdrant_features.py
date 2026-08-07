"""
统一测试脚本
测试 RAG、记忆存储和知识图谱功能
"""

import sys
import os

# Project root on path for test convenience (rag is a proper package)
from rag.rag_energy_qa import EnergyRAGSystem
from rag.memory_storage import LongTermMemory
from rag.general_kg import KnowledgeGraph


def test_rag_system():
    """测试 RAG 问答系统"""
    print("=" * 60)
    print("测试 RAG 问答系统")
    print("=" * 60)
    print()

    rag = EnergyRAGSystem()

    # 测试关键词搜索
    print("[1] 关键词搜索测试:")
    results = rag.search_by_keyword("能耗", limit=3)
    print(f"  找到 {len(results)} 条结果")
    for r in results[:2]:
        print(f"  - {r['content'][:80]}...")
    print()

    # 测试多关键词搜索
    print("[2] 多关键词搜索测试:")
    results = rag.search_by_multiple_keywords(["能耗", "标准"], limit=3)
    print(f"  找到 {len(results)} 条结果")
    for r in results[:2]:
        print(f"  - 匹配关键词: {r['matched_keywords']}")
    print()

    # 测试问题回答
    print("[3] 问题回答测试:")
    question = "医院的能耗指标是多少？"
    answer = rag.answer_question(question)
    print(f"  问题: {question}")
    print(f"  找到关键词: {answer['keywords_found']}")
    print(f"  相关文档数: {answer['relevant_documents']}")
    print()


def test_memory_storage():
    """测试长期记忆存储"""
    print("=" * 60)
    print("测试长期记忆存储")
    print("=" * 60)
    print()

    memory = LongTermMemory()

    # 创建集合
    print("[1] 创建记忆存储集合:")
    memory.create_collections()
    print()

    # 存储对话
    print("[2] 存储对话测试:")
    session_id = "test_session_001"

    memory.store_conversation(
        session_id=session_id,
        user_message="什么是能耗定额？",
        ai_response="能耗定额是指...",
        metadata={'topic': '能耗概念', 'importance': 'high'}
    )

    memory.store_conversation(
        session_id=session_id,
        user_message="如何计算人均能耗？",
        ai_response="人均能耗计算公式为...",
        metadata={'topic': '能耗计算', 'importance': 'medium'}
    )
    print()

    # 存储知识
    print("[3] 存储知识测试:")
    memory.store_knowledge(
        knowledge_type='energy_standard',
        content="《党政机关能源消耗定额标准》(DB37/T 2672-2019)",
        source="能耗审计报告",
        metadata={'standard': 'DB37/T 2672-2019'}
    )
    print()

    # 搜索对话
    print("[4] 搜索对话测试:")
    conversations = memory.search_conversations(session_id=session_id, limit=5)
    print(f"  找到 {len(conversations)} 条对话")
    for conv in conversations:
        print(f"  - {conv['user_message'][:50]}...")
    print()

    # 搜索知识
    print("[5] 搜索知识测试:")
    knowledge = memory.search_knowledge(keyword="能耗", limit=5)
    print(f"  找到 {len(knowledge)} 条知识")
    for k in knowledge:
        print(f"  - [{k['knowledge_type']}] {k['content'][:50]}...")
    print()

    # 获取统计信息
    print("[6] 记忆统计信息:")
    stats = memory.get_memory_stats()
    print(f"  对话历史: {stats['conversations']['count']} 条")
    print(f"  知识库: {stats['knowledge']['count']} 条")
    print()


def test_knowledge_graph():
    """测试知识图谱查询"""
    print("=" * 60)
    print("测试知识图谱查询")
    print("=" * 60)
    print()

    kg = KnowledgeGraph()

    # 获取集合信息
    print("[1] 集合信息:")
    info = kg.get_collection_info()
    for name, details in info.items():
        print(f"  {name}: {details['points_count']} 条数据")
    print()

    # 跨集合搜索
    print("[2] 跨集合搜索测试:")
    results = kg.cross_collection_search("能耗", limit_per_collection=3)
    print(f"  star_charts: {results['star_charts']['count']} 条")
    print(f"  knowledge_segment: {results['knowledge_segment']['count']} 条")
    print(f"  总计: {results['total_results']} 条")
    print()

    # 构建知识图谱
    print("[3] 构建知识图谱测试:")
    knowledge_map = kg.build_knowledge_map()
    print(f"  文档总数: {knowledge_map['total_documents']}")
    print(f"  分段总数: {knowledge_map['total_chunks']}")
    print(f"  知识类型:")
    for ktype, doc_ids in knowledge_map['knowledge_types'].items():
        print(f"    {ktype}: {len(doc_ids)} 个文档")
    print()

    # 文档摘要测试
    print("[4] 文档摘要测试:")
    if knowledge_map['documents']:
        first_doc_id = list(knowledge_map['documents'].keys())[0]
        summary = kg.get_document_summary(first_doc_id)
        print(f"  文档ID: {summary.get('document_id', 'N/A')}")
        print(f"  分段数: {summary.get('chunks_count', 0)}")
        print(f"  摘要: {summary.get('summary', 'N/A')}")
    print()


def main():
    """主函数"""
    print("=" * 60)
    print("Qdrant 功能统一测试")
    print("=" * 60)
    print()

    try:
        # 测试 RAG 系统
        test_rag_system()

        # 测试记忆存储
        test_memory_storage()

        # 测试知识图谱
        test_knowledge_graph()

        print("=" * 60)
        print("所有测试完成！")
        print("=" * 60)

    except Exception as e:
        print(f"测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()