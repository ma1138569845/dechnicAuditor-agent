"""轻量 LLM 客户端：管理制度提炼、参考报告段落仿写。

复用 rag 的 DeepSeek 直连模式（环境变量 DEEPSEEK_API_KEY / DEEPSEEK_API_BASE），
模型取 energy_audit config.yaml 的 rag.deepseek_model（默认 deepseek-v4-flash）。
无 key / 调用失败时返回 None，调用方降级到兜底文案，不阻塞报告生成。
"""

import os
from typing import List, Optional

_DEFAULT_MODEL = "deepseek-v4-flash"


def _model() -> str:
    m = os.environ.get("DEEPSEEK_MODEL") or os.environ.get("SUMMARY_MODEL")
    if not m:
        try:
            from tools.energy_audit.db_config import _from_local_config
            m = _from_local_config("rag", "deepseek_model")
        except Exception:
            m = None
    return (m or _DEFAULT_MODEL).strip()


def _api_key() -> str:
    return os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY", "")


def _api_base() -> str:
    return os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")


def _chat(messages, temperature=0.3, max_tokens=1200, task="energy_audit_management") -> Optional[str]:
    """单次 LLM 调用：优先 Hermes auxiliary client，回退 DeepSeek 直连。失败返回 None。"""
    try:
        from agent.auxiliary_client import call_llm

        resp = call_llm(
            task=task,
            provider="deepseek",
            model=_model(),
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if resp and getattr(resp, "choices", None):
            return resp.choices[0].message.content.strip()
    except Exception:
        pass

    key = _api_key()
    if not key:
        print("[llm_client] 未配置 DEEPSEEK_API_KEY，跳过 LLM 提炼")
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=key, base_url=_api_base())
        resp = client.chat.completions.create(
            model=_model(),
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content.strip() if resp.choices else None
    except Exception as e:  # noqa: BLE001
        print(f"[llm_client] LLM 调用失败: {e}")
        return None


def summarize_management_docs(doc_texts: List[str], unit_name: str) -> Optional[dict]:
    """从制度文件全文提炼第三章 3.1「机构职责」/ 3.2「目标方针」正文。

    Returns:
        {'org': str, 'goals_policy': str}；失败或文本为空返回 None。
    """
    texts = [t for t in doc_texts if t and t.strip()]
    if not texts:
        return None

    doc = "\n\n".join(f"[文件{i + 1}]\n{t}" for i, t in enumerate(texts))
    if len(doc) > 24000:
        doc = doc[:24000] + "\n\n[...内容过长已截断...]"

    system = (
        "你是能源审计报告撰写助手。请根据给定的能源管理制度文件内容，"
        "提炼出规范、通顺的中文正文，直接用于报告的正式章节。"
    )

    org = _chat([
        {"role": "system", "content": system},
        {"role": "user", "content": (
            f"被审计单位：{unit_name}\n\n制度文件内容：\n\n{doc}\n\n"
            "请提炼「能源资源管理机构职责」：组织架构、岗位设置、各层级职责分工。"
            "以连贯段落输出，不要列表标题，不要输出与职责无关的内容。"
            "若文件中未涉及，据实写一句说明。"
        )},
    ])

    goals = _chat([
        {"role": "system", "content": system},
        {"role": "user", "content": (
            f"被审计单位：{unit_name}\n\n制度文件内容：\n\n{doc}\n\n"
            "请提炼「能源资源管理目标和方针」：节能目标、管理方针、考核要求。"
            "以连贯段落输出，不要列表标题，不要输出与目标方针无关的内容。"
            "若文件中未涉及，据实写一句说明。"
        )},
    ])

    if not org and not goals:
        return None
    return {"org": (org or "").strip(), "goals_policy": (goals or "").strip()}


def imitate_from_structure(
    *,
    unit_name: str,
    chapter: str,
    section: str,
    outline_text: str,
    project_facts: str,
    reference_excerpt: str,
) -> Optional[str]:
    """按参考报告段落结构，用当前项目数据仿写正式报告段落。失败返回 None。"""
    section_hint = f"（{section}）" if section else ""
    excerpt = (reference_excerpt or "").strip()
    if len(excerpt) > 6000:
        excerpt = excerpt[:6000] + "\n\n[...参考文本过长已截断...]"

    facts = (project_facts or "").strip() or "（当前项目未提供可用数据）"
    outline = (outline_text or "").strip() or "（未能解析出明确小节结构，按规范报告段落撰写）"

    system = (
        "你是能源审计报告撰写助手。你的任务是仿写正式报告段落："
        "严格沿用参考报告的段落结构与公文语气，但只使用当前被审计单位的真实数据。"
        "禁止照抄参考报告中的单位名称、人数、面积、能耗数字或其他事实。"
        "数据缺失时用一句说明，不要编造。"
        "直接输出可用于报告的中文正文，不要前言、不要解释写作过程。"
    )
    user = (
        f"被审计单位：{unit_name}\n"
        f"目标章节：{chapter}{section_hint}\n\n"
        f"【参考段落结构】\n{outline}\n\n"
        f"【当前项目数据】\n{facts}\n\n"
        f"【参考报告原文（只学结构与语气，不抄事实）】\n{excerpt or '（无参考原文）'}\n\n"
        "请按上述结构仿写本项目对应段落。保留小节标题（如 3.1 …），"
        "图表位置用「（此处插图/表）」占位，不要输出 Markdown 代码围栏。"
    )
    return _chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.35,
        max_tokens=2500,
        task="energy_audit_imitate",
    )
