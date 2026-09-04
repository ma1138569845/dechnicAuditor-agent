"""
能源审计工具包
提供能源审计相关的数据处理、查询、检索和报告生成功能
"""

import os

__version__ = '2.0.0'
__author__ = '马天远'

__all__ = [
    'ExcelDataProcessor',
    'PgDataQuery',
    'RAGKnowledgeRetrieval',
    'ReportGenerator'
]


def __getattr__(name: str):
    """延迟导入重依赖模块，避免无条件加载 pandas / qdrant 等。"""
    if name == "ExcelDataProcessor":
        from .excel_processor import ExcelDataProcessor
        return ExcelDataProcessor
    if name == "PgDataQuery":
        from .pg_query import PgDataQuery
        return PgDataQuery
    if name == "RAGKnowledgeRetrieval":
        from rag.rag_retrieval import RAGKnowledgeRetrieval
        return RAGKnowledgeRetrieval
    if name == "ReportGenerator":
        from .report_generator import ReportGenerator
        return ReportGenerator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# 配置示例（凭据从环境变量读取，切勿在此写入）
# RAG 连接信息走 rag.config → config.yaml knowledge_base:（与 Desktop 知识库同一套）
DEFAULT_CONFIG = {
    'database': {
        'host': os.environ.get('DB_HOST', '10.10.1.165'),
        'port': os.environ.get('DB_PORT', '5432'),
        'database': os.environ.get('DB_NAME', 'dc_energy_audit2'),
        'user': os.environ.get('DB_USER', 'postgres'),
        'password': os.environ.get('DB_PASSWORD', ''),
        'sslmode': os.environ.get('DB_SSLMODE', 'prefer'),
    },
    'output': {
        'format': 'markdown',
        'directory': './reports',
    },
}
