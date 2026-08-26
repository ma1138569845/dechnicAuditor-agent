#!/usr/bin/env python3
"""
基于 LlamaIndex + DeepSeek (LLM) + Qwen (向量) + Qdrant 的文档问答系统

架构（两阶段）:
  索引阶段（离线执行一次）:
    加载文档 → 切块 → Qwen 向量化 → 存入 Qdrant (1024维)
  查询阶段（每次提问）:
    问题 → Qwen 向量化 → Qdrant 检索相似块 → 上下文 + 问题 → DeepSeek 生成答案

模型分工:
  - LLM (生成答案):  DeepSeek deepseek-v4-flash  (OpenAI 兼容, 需 DEEPSEEK_API_KEY)
  - 向量 (嵌入):     Qwen text-embedding-v3      (1024维, 匹配 knowledge_segment, 需 DASHSCOPE_API_KEY)
  - 向量库:          Qdrant 10.10.2.55:6333      (复用 knowledge_segment 集合)

环境变量:
  DEEPSEEK_API_KEY    - DeepSeek API Key (必需)
  DASHSCOPE_API_KEY   - 阿里云百炼 API Key, 用于 Qwen 向量模型 (必需)
  可选:
  DEEPSEEK_MODEL      - 默认 deepseek-v4-flash
  QWEN_EMBED_MODEL    - 默认 text-embedding-v3
  QWEN_EMBED_DIM      - 默认 1024 (text-embedding-v3 标准维度)
  QDRANT_URL          - 默认 http://127.0.0.1:6333
  QDRANT_COLLECTION   - 默认 knowledge_segment
"""

import os
import argparse
from typing import Optional

from llama_index.core import (
    VectorStoreIndex,
    SimpleDirectoryReader,
    StorageContext,
    Settings,
)
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.vector_stores import (
    MetadataFilters,
    MetadataFilter,
    FilterOperator,
)

# Qdrant 集成
from qdrant_client import QdrantClient
from llama_index.vector_stores.qdrant import QdrantVectorStore

# LLM: DeepSeek (OpenAI 兼容格式)
from llama_index.llms.openai import OpenAI
# 向量: Qwen (通过 DashScope OpenAI 兼容端点调用)
from llama_index.embeddings.openai import OpenAIEmbedding


# ============ 配置 ============
# Runtime values come from rag.config (config.yaml knowledge_base: / .env).
# Module-level names remain for callers that imported them historically.


def _qdrant_url() -> str:
    try:
        from rag.config import qdrant_http_url

        return qdrant_http_url()
    except Exception:
        return os.getenv("QDRANT_URL", "http://127.0.0.1:6333")


def _default_collection() -> str:
    try:
        from rag.config import energy_audit_collection

        return energy_audit_collection()
    except Exception:
        return os.getenv("QDRANT_COLLECTION", "knowledge_segment_qwen")


QDRANT_URL = _qdrant_url()
DEFAULT_COLLECTION = _default_collection()
DOCS_DIR = "./docs"

# DeepSeek LLM 配置
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")

# Qwen 向量模型配置 (阿里云百炼 DashScope, OpenAI 兼容模式)
# 注意: 每次调用 init_models() 时动态读取环境变量，避免模块导入时缓存旧 key
DASHSCOPE_BASE_URL = os.getenv(
    "DASHSCOPE_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
)
QWEN_EMBED_MODEL = os.getenv("QWEN_EMBED_MODEL", "text-embedding-v3")
QWEN_EMBED_DIM = int(os.getenv("QWEN_EMBED_DIM", "1024"))  # text-embedding-v3 = 1024 维


def check_keys() -> list:
    """检查必要的 API Key 是否已配置, 返回缺失项列表"""
    missing = []
    if not DEEPSEEK_API_KEY:
        missing.append("DEEPSEEK_API_KEY")
    if not os.getenv("DASHSCOPE_API_KEY", ""):
        missing.append("DASHSCOPE_API_KEY")
    return missing


def _register_models() -> None:
    """把 DeepSeek / Qwen 模型登记进 LlamaIndex 的 OpenAI 包装层名册。

    LlamaIndex 的 OpenAI 包装层有两处对非 OpenAI 官方模型名会 raise:

    LLM 侧 (DeepSeek):
      1. ``ALL_AVAILABLE_MODELS`` 查 context window, 名册外 -> complete/chat 直接 ValueError;
      2. ``CHAT_MODELS`` 判定是否走 /v1/chat/completions, 否则回退老式 /v1/completions
         —— 而 DeepSeek 已把老式 completions 隔到 /beta, 走 chat 才是正路。
      两表各补登记 deepseek-* (上下文 128k)。

    向量侧 (Qwen text-embedding-v3):
      1. ``OpenAIEmbeddingModelType`` 是 Enum, 名册外 -> 构造时 ValueError;
      2. ``get_engine(mode, model, mode_model_dict)`` 查老式 ada 引擎名表, 名册外 -> ValueError。
      对 (1) 把模型名塞进 enum 的 ``_value2member_map_`` 使其通过校验;
      对 (2) monkeypatch ``get_engine`` 对未知模型透传模型名本身 (第三方端点直接用
      ``model`` 字段, engine 名不影响请求体, 仅是 LlamaIndex 内部占位)。
    """
    from llama_index.llms.openai import utils as _ou

    # --- LLM: DeepSeek ---
    deepseek_models = {
        "deepseek-v4-flash": 131072,
        "deepseek-v4-pro": 131072,
        "deepseek-chat": 131072,
        "deepseek-reasoner": 131072,
    }
    for name, ctx in deepseek_models.items():
        if name not in _ou.ALL_AVAILABLE_MODELS:
            _ou.ALL_AVAILABLE_MODELS[name] = ctx
        if name not in _ou.CHAT_MODELS:
            _ou.CHAT_MODELS[name] = ctx

    # --- 向量: Qwen text-embedding-v3 ---
    from llama_index.embeddings.openai import base as _oeb

    qwen_embeds = ["text-embedding-v3", "text-embedding-v2", "text-embedding-v1"]
    for name in qwen_embeds:
        if name not in _oeb.OpenAIEmbeddingModelType._value2member_map_:
            _oeb.OpenAIEmbeddingModelType._value2member_map_[name] = name

    if not getattr(_oeb.get_engine, "_hermes_patched", False):
        _orig_get_engine = _oeb.get_engine

        def _safe_get_engine(mode, model, mode_model_dict):
            try:
                return _orig_get_engine(mode, model, mode_model_dict)
            except ValueError:
                # 未知模型 (如 Qwen): engine 名就用模型名本身, 透传给第三方端点
                return model

        _safe_get_engine._hermes_patched = True  # type: ignore[attr-defined]
        _oeb.get_engine = _safe_get_engine


def init_models() -> None:
    """
    初始化模型:
      - LLM:     DeepSeek (deepseek-v4-flash)
      - 向量模型: Qwen text-embedding-v3 (1024 维, 匹配 knowledge_segment)
    """
    missing = check_keys()
    if missing:
        raise EnvironmentError(
            "缺少 API Key: " + ", ".join(missing) + "\n"
            "请设置环境变量后重试:\n"
            "  Windows:  set DEEPSEEK_API_KEY=sk-xxx\n"
            "  Windows:  set DASHSCOPE_API_KEY=sk-xxx\n"
            "  Linux:    export DEEPSEEK_API_KEY=sk-xxx ; export DASHSCOPE_API_KEY=sk-xxx"
        )

    # 先把 DeepSeek 登记进 LlamaIndex 的模型名册 (见 _register_models 注释)
    _register_models()

    # --- LLM: DeepSeek (OpenAI 兼容) ---
    Settings.llm = OpenAI(
        model=DEEPSEEK_MODEL,
        api_base=DEEPSEEK_BASE_URL,
        api_key=DEEPSEEK_API_KEY,
        temperature=0.3,
        max_tokens=2048,
    )

    # --- 向量模型: Qwen text-embedding-v3 ---
    # Qwen 通过 DashScope 的 OpenAI 兼容端点提供 embedding 服务
    # 注意: DashScope 兼容端点不接受 dimensions 参数 (传了会报 Required body invalid),
    #       text-embedding-v3 默认输出 1024 维, 正好匹配 knowledge_segment, 无需指定。
    Settings.embed_model = OpenAIEmbedding(
        model=QWEN_EMBED_MODEL,
        api_base=DASHSCOPE_BASE_URL,
        api_key=os.getenv("DASHSCOPE_API_KEY", ""),
        embed_batch_size=10,  # DashScope embedding 批量上限较低, 建议 10-25
    )


def get_qdrant_client() -> QdrantClient:
    """连接到 Qdrant 实例 (走 gRPC 绕开 httpx HTTP/2 超时)。

    该 Qdrant 实例 (10.10.2.55) 经 httpx 走 REST 会反复 timeout (HTTP/2 兼容问题),
    而 curl/requests 走 HTTP/1.1 正常。实测同实例的 gRPC 6334 端口 0.x 秒即可连通,
    故默认走 gRPC。如需强制 REST, 设环境变量 QDRANT_USE_GRPC=0。
    """
    use_grpc = os.getenv("QDRANT_USE_GRPC", "1") != "0"
    try:
        from rag.config import qdrant_grpc_port, qdrant_http_port

        grpc_port = qdrant_grpc_port()
        http_port = qdrant_http_port()
    except Exception:
        grpc_port, http_port = 6334, 6333
    return QdrantClient(
        url=_qdrant_url(),
        prefer_grpc=use_grpc,
        port=grpc_port if use_grpc else http_port,
        grpc_port=grpc_port,
        timeout=60,
        check_compatibility=False,
    )


def get_vector_store(collection_name: str) -> QdrantVectorStore:
    """创建指向指定集合的 Qdrant 向量存储"""
    client = get_qdrant_client()
    return QdrantVectorStore(
        client=client,
        collection_name=collection_name,
        enable_hybrid=False,  # 纯稠密检索；需要 BM25+SPLADE 混合可打开
    )


def build_index(
    docs_dir: str = DOCS_DIR,
    collection_name: str = DEFAULT_COLLECTION,
    chunk_size: int = 1024,
    chunk_overlap: int = 200,
) -> Optional[VectorStoreIndex]:
    """从文档构建索引并写入 Qdrant"""
    if not os.path.exists(docs_dir):
        os.makedirs(docs_dir)
        print(f"已创建目录 {docs_dir}，请把文档（PDF/TXT/MD）放进去后重跑")
        return None

    documents = SimpleDirectoryReader(docs_dir).load_data()
    if not documents:
        print(f"目录 {docs_dir} 中没有文档")
        return None

    # 给文档打元数据标签（教程中的自定义元数据技巧）
    for doc in documents:
        # SimpleDirectoryReader 默认会带 file_name / page_label
        doc.metadata.setdefault("source", doc.metadata.get("file_name", "unknown"))
        doc.metadata.setdefault("department", "engineering")
        doc.metadata.setdefault("doc_type", "general")

    print(f"加载了 {len(documents)} 个文档，开始切分...")

    # 文本切分：SentenceSplitter 按句子边界切，保留 chunk_overlap 防止信息被切断
    parser = SentenceSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    nodes = parser.get_nodes_from_documents(documents)
    print(f"切成了 {len(nodes)} 个块")

    # 接入 Qdrant
    vector_store = get_vector_store(collection_name)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    print(f"正在生成嵌入并写入 Qdrant 集合 [{collection_name}] ...")
    index = VectorStoreIndex.from_documents(
        documents,
        storage_context=storage_context,
        show_progress=True,
    )
    print(f"索引已写入 Qdrant: {QDRANT_URL}")
    return index


def load_index(collection_name: str = DEFAULT_COLLECTION) -> VectorStoreIndex:
    """从 Qdrant 加载已有索引（Qdrant 天然持久化，无需 persist_dir）"""
    vector_store = get_vector_store(collection_name)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    # Qdrant 自带持久化，直接从向量存储构建索引即可
    return VectorStoreIndex.from_vector_store(
        vector_store,
        storage_context=storage_context,
    )


def make_query_engine(
    index: VectorStoreIndex,
    top_k: int = 5,
    response_mode: str = "compact",
    filters: Optional[MetadataFilters] = None,
):
    """
    创建查询引擎
    response_mode:
      - compact:  最快，全部块塞一个 prompt
      - refine:   逐块精炼，质量高但慢
      - tree_summarize: 树状汇总，适合综合性问题
    """
    return index.as_query_engine(
        similarity_top_k=top_k,
        response_mode=response_mode,
        filters=filters,
    )


def query(
    question: str,
    collection_name: str = DEFAULT_COLLECTION,
    top_k: int = 5,
    response_mode: str = "compact",
    department: Optional[str] = None,
) -> None:
    """执行一次问答"""
    index = load_index(collection_name)

    # 元数据过滤（教程中的 MetadataFilters 技巧）
    filters = None
    if department:
        filters = MetadataFilters(
            filters=[
                MetadataFilter(
                    key="department",
                    value=department,
                    operator=FilterOperator.EQ,
                )
            ]
        )

    engine = make_query_engine(index, top_k=top_k, response_mode=response_mode, filters=filters)
    print(f"\n正在检索 Qdrant + 生成答案 (top_k={top_k}, mode={response_mode})...")

    response = engine.query(question)
    print(f"\n回答: {response}")

    if response.source_nodes:
        print("\n--- 参考来源 ---")
        for i, node in enumerate(response.source_nodes, 1):
            source = node.metadata.get("file_name") or node.metadata.get("source", "未知")
            score = node.score if node.score is not None else "N/A"
            print(f"  [{i}] {source} (相似度: {score})")


def interactive(collection_name: str = DEFAULT_COLLECTION) -> None:
    """交互式问答循环"""
    index = load_index(collection_name)
    engine = make_query_engine(index, top_k=5, response_mode="compact")

    print("\n文档问答系统 (DeepSeek + Qwen + Qdrant) 已启动")
    print("命令: quit/exit 退出 | rebuild 重建索引 | mode <compact|refine|tree_summarize> 切换模式")
    print(f"Qdrant: {QDRANT_URL} | 集合: {collection_name} | LLM: {DEEPSEEK_MODEL} | 向量: {QWEN_EMBED_MODEL}")
    print("-" * 70)

    while True:
        question = input("\n你的问题: ").strip()
        if question.lower() in ("quit", "exit", "q"):
            break
        if not question:
            continue
        if question.lower() == "rebuild":
            index = build_index(collection_name=collection_name)
            if index:
                engine = make_query_engine(index)
            continue
        if question.lower().startswith("mode "):
            mode = question.split(" ", 1)[1].strip()
            print(f"response_mode → {mode}")
            engine = make_query_engine(index, response_mode=mode)
            continue

        print("\n正在检索和生成答案...")
        response = engine.query(question)
        print(f"\n回答: {response}")
        if response.source_nodes:
            print("\n--- 参考来源 ---")
            for i, node in enumerate(response.source_nodes, 1):
                source = node.metadata.get("file_name") or node.metadata.get("source", "未知")
                print(f"  [{i}] {source}")


def main():
    parser = argparse.ArgumentParser(
        description="LlamaIndex + DeepSeek + Qwen + Qdrant 文档问答系统"
    )
    sub = parser.add_subparsers(dest="action", required=True)

    sub.add_parser("build", help="从 ./docs 构建索引写入 Qdrant")
    sub.add_parser("chat", help="交互式问答")

    q = sub.add_parser("query", help="单次问答")
    q.add_argument("question")
    q.add_argument("--collection", default=DEFAULT_COLLECTION)
    q.add_argument("--top-k", type=int, default=5)
    q.add_argument(
        "--mode", default="compact",
        choices=["compact", "refine", "tree_summarize"],
    )
    q.add_argument("--department", help="按部门元数据过滤检索")

    args = parser.parse_args()

    # 配置检查
    missing = check_keys()
    if missing:
        print(f"缺少 API Key: {', '.join(missing)}")
        print("\n请先设置环境变量:")
        print("  Windows:  set DEEPSEEK_API_KEY=sk-你的key")
        print("  Windows:  set DASHSCOPE_API_KEY=sk-你的key")
        print("  Linux:    export DEEPSEEK_API_KEY=sk-你的key ; export DASHSCOPE_API_KEY=sk-你的key")
        return

    init_models()

    if args.action == "build":
        build_index()
    elif args.action == "chat":
        interactive()
    elif args.action == "query":
        query(
            args.question,
            collection_name=args.collection,
            top_k=args.top_k,
            response_mode=args.mode,
            department=args.department,
        )


if __name__ == "__main__":
    main()