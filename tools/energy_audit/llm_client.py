"""轻量 LLM 客户端：能源管理制度文件 → 第三章 3.1/3.2 正文提炼。

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


def _chat(messages, temperature=0.3, max_tokens=1200) -> Optional[str]:
    """单次 LLM 调用：优先 Hermes auxiliary client，回退 DeepSeek 直连。失败返回 None。"""
    try:
        from agent.auxiliary_client import call_llm

        resp = call_llm(
            task="energy_audit_management",
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