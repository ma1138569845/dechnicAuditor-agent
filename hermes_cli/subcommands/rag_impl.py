"""``hermes rag`` implementation (interactive RAG knowledge-base wizard).

Extracted from the customized hermes_cli/main.py to keep the CLI entry point
lean. The parser is built in :mod:`hermes_cli.subcommands.rag`.
"""

from __future__ import annotations

import os
import sys


def _require_tty(command_name: str) -> None:
    """Exit with a clear error if stdin is not a terminal."""
    if not sys.stdin.isatty():
        print(
            f"Error: 'hermes {command_name}' requires an interactive terminal.\n"
            f"It cannot be run through a pipe or non-interactive subprocess.\n"
            f"Run it directly in your terminal instead.",
            file=sys.stderr,
        )
        sys.exit(1)


def cmd_rag(args):
    """Configure RAG knowledge base — interactive wizard for Qdrant, embedding, LLM, storage."""
    _require_tty("rag")
    configure_rag_interactive(args)


def configure_rag_interactive(args=None) -> None:
    """Interactive RAG configuration wizard.

    Walks the user through:
      1. Remote Qdrant connection (host, port, API key)
      2. Embedding model (DashScope API key, model name)
      3. LLM model (DeepSeek API key, model, base URL)
      4. Initialize local rag/data/ directories
      5. Initialize Qdrant collections
      6. Initialize SQLite metadata tables
      7. Write ``knowledge_base:`` into Hermes config.yaml (secrets into .env)
    """
    from pathlib import Path

    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.prompt import Prompt, Confirm
        from rich.table import Table
        from rich import print as rprint
    except ImportError:
        # Fallback to plain print/input when Rich is not available
        Console = None
        Panel = None
        Prompt = None
        Confirm = None
        Table = None
        def rprint(*a, **kw):
            print(*a)

    _RICH = Console is not None

    def _prompt(prompt_text: str, default: str = "", password: bool = False) -> str:
        """Prompt helper that works with or without Rich."""
        if _RICH and Prompt is not None:
            return Prompt.ask(prompt_text, default=default, password=password) or default
        if password:
            import getpass
            value = getpass.getpass(f"{prompt_text} [{default}]: ")
        else:
            value = input(f"{prompt_text} [{default}]: ")
        return value.strip() or default

    def _confirm(prompt_text: str, default: bool = True) -> bool:
        if _RICH and Confirm is not None:
            return Confirm.ask(prompt_text, default=default)
        yn = "Y/n" if default else "y/N"
        answer = input(f"{prompt_text} [{yn}]: ").strip().lower()
        if not answer:
            return default
        return answer in ("y", "yes")

    # ------------------------------------------------------------------
    # Resolve rag/ package root
    # ------------------------------------------------------------------
    _RAG_DIR = Path(__file__).parent.parent / "rag"   # 代码模块目录
    try:
        from hermes_constants import get_hermes_home as _get_hermes_home
    except ImportError:
        _get_hermes_home = lambda: Path.home() / ".hermes"
    _HERMES_RAG = _get_hermes_home() / "rag"           # 用户数据目录（对标 skills）
    _DATA_DIR = _HERMES_RAG / "data"
    _CONFIG_YAML = _HERMES_RAG / "qdrant_config.yaml"  # 配置文件也在用户数据目录

    non_interactive = getattr(args, "non_interactive", False)

    # ------------------------------------------------------------------
    # 1. Qdrant remote config
    # ------------------------------------------------------------------
    rprint()
    if _RICH and Panel is not None:
        rprint(Panel.fit(
            "[bold]Qdrant 远端配置[/bold]\n"
            "配置远程 Qdrant 向量数据库连接信息。",
            title="📡 Step 1/5",
        ))
    else:
        rprint("=" * 60)
        rprint("  Step 1/5: Qdrant 远端配置")
        rprint("=" * 60)

    qdrant_host = getattr(args, "qdrant_host", None) or (
        os.environ.get("QDRANT_HOST", "127.0.0.1") if non_interactive
        else _prompt("Qdrant 服务器地址", default=os.environ.get("QDRANT_HOST", "127.0.0.1"))
    )
    qdrant_port = getattr(args, "qdrant_port", None) or (
        6334 if non_interactive else int(_prompt("Qdrant gRPC 端口", default="6334"))
    )
    qdrant_api_key = getattr(args, "qdrant_api_key", None) or (
        "" if non_interactive else _prompt("Qdrant API Key（无认证留空）", default="", password=True)
    )

    if not getattr(args, "skip_qdrant", False):
        rprint("\n  ⏳ 测试 Qdrant 连接...")
        try:
            from qdrant_client import QdrantClient
            client_kwargs = {"host": qdrant_host, "port": qdrant_port}
            if qdrant_api_key:
                client_kwargs["api_key"] = qdrant_api_key
            client = QdrantClient(**client_kwargs)
            # gRPC health check
            client.get_collections()
            rprint("  ✓ Qdrant 连接成功")
        except Exception as e:
            rprint(f"  ⚠ Qdrant 连接失败: {e}")
            if non_interactive:
                rprint("  ⏭ 非交互模式：自动跳过，继续配置。")
            elif not _confirm("跳过 Qdrant 连接检查，继续配置？", default=True):
                rprint("  已取消。")
                return
    else:
        rprint("\n  ⏭ 跳过 Qdrant 连接检查 (--skip-qdrant)")

    # ------------------------------------------------------------------
    # 2. Embedding model config
    # ------------------------------------------------------------------
    rprint()
    if _RICH and Panel is not None:
        rprint(Panel.fit(
            "[bold]Embedding 模型配置[/bold]\n"
            "配置 DashScope 文本嵌入模型。",
            title="🧬 Step 2/5",
        ))
    else:
        rprint("=" * 60)
        rprint("  Step 2/5: Embedding 模型配置")
        rprint("=" * 60)

    embedding_model = getattr(args, "embedding_model", None) or (
        "dashscope/text-embedding-v3" if non_interactive else _prompt("Embedding 模型", default="dashscope/text-embedding-v3")
    )
    dashscope_api_key = getattr(args, "dashscope_api_key", None) or (
        "" if non_interactive else _prompt("DashScope API Key", default="", password=True)
    )

    if dashscope_api_key:
        rprint("  ⏳ 测试 Embedding API...")
        try:
            from openai import OpenAI
            emb_client = OpenAI(
                api_key=dashscope_api_key,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            )
            resp = emb_client.embeddings.create(
                model=embedding_model.replace("dashscope/", ""),
                input=["test"],
            )
            rprint(f"  ✓ Embedding API 正常 (维度: {len(resp.data[0].embedding)})")
        except Exception as e:
            rprint(f"  ⚠ Embedding API 测试失败: {e}")
    else:
        rprint("  ⚠ 未设置 DashScope API Key，跳过 Embedding 测试")

    # ------------------------------------------------------------------
    # 3. LLM model config
    # ------------------------------------------------------------------
    rprint()
    if _RICH and Panel is not None:
        rprint(Panel.fit(
            "[bold]LLM 模型配置[/bold]\n"
            "配置用于摘要生成和 Wiki 编写的 LLM。",
            title="🤖 Step 3/5",
        ))
    else:
        rprint("=" * 60)
        rprint("  Step 3/5: LLM 模型配置")
        rprint("=" * 60)

    llm_model = getattr(args, "llm_model", None) or (
        "deepseek-v4-flash" if non_interactive else _prompt("LLM 模型", default="deepseek-v4-flash")
    )
    deepseek_api_key = getattr(args, "deepseek_api_key", None) or (
        "" if non_interactive else _prompt("DeepSeek API Key（可复用 OpenAI 兼容的 Key）", default="", password=True)
    )
    deepseek_api_base = getattr(args, "deepseek_api_base", None) or (
        "https://api.deepseek.com/v1" if non_interactive else _prompt("DeepSeek API Base URL", default="https://api.deepseek.com/v1")
    )

    if deepseek_api_key:
        rprint("  ⏳ 测试 LLM API...")
        try:
            from openai import OpenAI
            llm_client = OpenAI(
                api_key=deepseek_api_key,
                base_url=deepseek_api_base,
            )
            resp = llm_client.chat.completions.create(
                model=llm_model,
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=5,
            )
            rprint(f"  ✓ LLM API 正常 (模型: {resp.model})")
        except Exception as e:
            rprint(f"  ⚠ LLM API 测试失败: {e}")
    else:
        rprint("  ⚠ 未设置 LLM API Key，跳过 LLM 测试")

    # ------------------------------------------------------------------
    # 4. Initialize local directories & SQLite
    # ------------------------------------------------------------------
    rprint()
    if _RICH and Panel is not None:
        rprint(Panel.fit(
            "[bold]本地存储初始化[/bold]\n"
            "创建 rag/data/ 目录和 SQLite 元数据库。",
            title="📁 Step 4/5",
        ))
    else:
        rprint("=" * 60)
        rprint("  Step 4/5: 本地存储初始化")
        rprint("=" * 60)

    # Create default KB directories (3 KB × 本地文档存储)
    for kb_id in (
        "energy_audit_reports",
        "energy_quota_standards",
        "energy_audit_technical_guidelines",
    ):
        kb_dir = _DATA_DIR / kb_id
        kb_dir.mkdir(parents=True, exist_ok=True)
        rprint(f"  ✓ 文档目录: {kb_dir}")

    # Create Wiki vault directory (Karpathy-style markdown wiki, Obsidian-compatible)
    wiki_vault = _HERMES_RAG / "wiki" / "generated"
    wiki_vault.mkdir(parents=True, exist_ok=True)
    rprint(f"  ✓ Wiki Vault: {wiki_vault}")

    # Initialize SQLite — use the authoritative _init_schema to ensure all tables
    db_path = _DATA_DIR / ".knowledge_meta.db"
    try:
        import sqlite3
        from rag.api.knowledge_base import _init_schema, _ensure_default_kb, _DEFAULT_KBS

        conn = sqlite3.connect(str(db_path))
        _init_schema(conn)
        conn.commit()
        conn.close()
        rprint(f"  ✓ SQLite 数据库（9 张表）: {db_path}")
        rprint(f"    - knowledge_bases, knowledge_folders, knowledge_documents, knowledge_chunks")
        rprint(f"    - vectorization_jobs, knowledge_entities, knowledge_relationships")
        rprint(f"    - knowledge_wiki_pages, knowledge_curation_jobs")
    except Exception as e:
        rprint(f"  ✗ SQLite 初始化失败: {e}")

    # Create default KB records (3 system KBs in metadata table)
    try:
        _ensure_default_kb()
        rprint("  ✓ 默认知识库记录已创建")
        for kb_def in _DEFAULT_KBS:
            rprint(f"    - {kb_def['id']}: {kb_def['name']}")
            rprint(f"      主集合={kb_def['qdrant_collection']}, 实体={kb_def['qdrant_collection']}_entities, Wiki={kb_def['qdrant_collection']}_wiki")
    except Exception as e:
        rprint(f"  ⚠ 默认知识库初始化警告: {e}")

    # ------------------------------------------------------------------
    # 5. Initialize Qdrant collections
    # ------------------------------------------------------------------
    rprint()
    if _RICH and Panel is not None:
        rprint(Panel.fit(
            "[bold]Qdrant 集合初始化[/bold]\n"
            "在远端 Qdrant 中创建向量集合。",
            title="🗄️ Step 5/5",
        ))
    else:
        rprint("=" * 60)
        rprint("  Step 5/5: Qdrant 集合初始化")
        rprint("=" * 60)

    if getattr(args, "skip_qdrant", False):
        rprint("  ⏭ 跳过 Qdrant 集合创建 (--skip-qdrant)")
    else:
        # Each KB has 3 collections: main (chunks), entities (graph), wiki (pages)
        kb_collections = []
        for kb_id in (
            "energy_audit_reports",
            "energy_quota_standards",
            "energy_audit_technical_guidelines",
        ):
            kb_collections.append((kb_id, 1024, "Cosine", "文档分段"))
            kb_collections.append((f"{kb_id}_entities", 1024, "Cosine", "知识实体"))
            kb_collections.append((f"{kb_id}_wiki", 1024, "Cosine", "Wiki 页面"))

        for col_name, vec_size, distance, desc in kb_collections:
            try:
                from qdrant_client.models import VectorParams, Distance

                distance_map = {"Cosine": Distance.COSINE, "Dot": Distance.DOT, "Euclid": Distance.EUCLID}
                existing = client.get_collections()
                existing_names = {c.name for c in existing.collections}

                if col_name in existing_names:
                    rprint(f"  ⏭ {col_name} ({desc}): 已存在")
                    continue

                client.create_collection(
                    collection_name=col_name,
                    vectors_config=VectorParams(size=vec_size, distance=distance_map.get(distance, Distance.COSINE)),
                )
                rprint(f"  ✓ {col_name} ({desc}, dim={vec_size}, dist={distance})")
            except Exception as e:
                rprint(f"  ✗ {col_name} ({desc}): {e}")

    # ------------------------------------------------------------------
    # Persist into Hermes config.yaml (the runtime source of truth)
    # ------------------------------------------------------------------
    rprint()
    rprint("  ⏳ 写入 Hermes config.yaml → knowledge_base ...")
    try:
        from hermes_cli.config import load_config, save_config, save_env_value

        cfg = load_config()
        kb = cfg.get("knowledge_base")
        if not isinstance(kb, dict):
            kb = {}
            cfg["knowledge_base"] = kb
        kb["qdrant_host"] = str(qdrant_host)
        kb["qdrant_port"] = int(qdrant_port)
        kb["embedding_model"] = str(embedding_model)
        kb["summary_model"] = str(llm_model)
        kb["deepseek_api_base"] = str(deepseek_api_base)
        save_config(cfg)
        from rag.config import clear_cache

        clear_cache()
        rprint(f"  ✓ 已写入 {_get_hermes_home() / 'config.yaml'} 的 knowledge_base 节")
        if dashscope_api_key:
            save_env_value("DASHSCOPE_API_KEY", dashscope_api_key)
            rprint("  ✓ DashScope API Key 已写入 .env")
        if deepseek_api_key:
            save_env_value("DEEPSEEK_API_KEY", deepseek_api_key)
            rprint("  ✓ DeepSeek API Key 已写入 .env")
        if qdrant_api_key:
            save_env_value("QDRANT_API_KEY", qdrant_api_key)
            rprint("  ✓ Qdrant API Key 已写入 .env")
        if _CONFIG_YAML.exists():
            _CONFIG_YAML.write_text(
                "# DEPRECATED. Runtime does not read this file.\n"
                f"# Edit {_get_hermes_home() / 'config.yaml'} → knowledge_base: instead.\n",
                encoding="utf-8",
            )
            rprint(f"  ℹ 旧文件 {_CONFIG_YAML} 已标记为废弃，不再作为配置源")
    except Exception as e:
        rprint(f"  ✗ 写入 config.yaml 失败: {e}")

    rprint()
    if _RICH and Table is not None:
        table = Table(title="RAG 配置摘要")
        table.add_column("项目", style="cyan")
        table.add_column("值", style="green")
        table.add_row("Qdrant 地址", f"{qdrant_host}:{qdrant_port}")
        table.add_row("Qdrant API Key", "已设置" if qdrant_api_key else "未设置（无认证）")
        table.add_row("Embedding 模型", embedding_model)
        table.add_row("DashScope Key", "已设置" if dashscope_api_key else "未设置")
        table.add_row("LLM 模型", llm_model)
        table.add_row("LLM Base URL", deepseek_api_base)
        table.add_row("DeepSeek Key", "已设置" if deepseek_api_key else "未设置")
        table.add_row("本地数据目录", str(_DATA_DIR))
        table.add_row("Wiki Vault", str(_HERMES_RAG / "wiki" / "generated"))
        table.add_row("配置文件", str(_get_hermes_home() / "config.yaml") + " → knowledge_base")
        table.add_row("SQLite 表", "9 张 (bases, folders, docs, chunks, vector_jobs, entities, relationships, wiki_pages, curation_jobs)")
        table.add_row("默认知识库", "3 个 × 3 集合 = 9 个 Qdrant 集合")
        rprint(table)
    else:
        rprint("=" * 60)
        rprint("  RAG 配置摘要")
        rprint("=" * 60)
        rprint(f"  Qdrant:         {qdrant_host}:{qdrant_port}")
        rprint(f"  Embedding:      {embedding_model}")
        rprint(f"  LLM:            {llm_model} @ {deepseek_api_base}")
        rprint(f"  本地数据:       {_DATA_DIR}")
        rprint(f"  Wiki Vault:     {_HERMES_RAG / 'wiki' / 'generated'}")
        rprint(f"  配置文件:       {_get_hermes_home() / 'config.yaml'} → knowledge_base")
        rprint(f"  SQLite 表:      9 张")
        rprint(f"  Qdrant 集合:    9 个 (3 KB × 主文档+实体+Wiki)")
        rprint(f"  默认知识库:     3 个")

    rprint()
    rprint("[bold green]✓ RAG 配置完成！[/bold green]" if _RICH else "✓ RAG 配置完成！")
    rprint(f"  本地数据目录: {_DATA_DIR}")
    rprint(f"  配置文件:     {_get_hermes_home() / 'config.yaml'} → knowledge_base")
    rprint()
    rprint("  运行 hermes rag 可重新配置。")
