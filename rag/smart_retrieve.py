#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多路召回 + 重排序（2026-09-20，设计 P3-1；对应《知识库优化计划》阶段 1.3）

计划的原设计：
    路1 向量语义 / 路2 标签精确 / 路3 关键字 / 路4 规则引擎
    重排序：relevance + recency + authority 加权

本实现落地为**四条可执行的召回路**（都复用既有函数，不复制逻辑）：
    R1 向量   `rag_search.search_qdrant(query, tags)`        —— 语义最相关
    R2 标签   `rag_search.search_by_tags(tags)`              —— 同类机构/章节池；**必须过关键字相关性闸**
    R3 关键字 本地：`reference_library.search_local_references`（成稿库，离线可用）
                     + `rag_search.search_wiki`（章节指南 / 生成 wiki 页）
    R4 权威   `rag_search.search_knowledge_graph`            —— 因果诊断候选；**标记为非报告**

重排序：final = 0.55×相关性 + 0.15×类型匹配 + 0.15×来源权威 + 0.15×时效

    ⚠️ 两条校准（都来自 2026-09-20 实测，不是拍脑袋）：
    1. **各路的 `score` 语义不同**：向量路/图谱路的分本身就是 0~1 相关性/置信度；
       标签路、本地成稿路的分是"匹配分"（本地库那是 2~3 的整数），混用会出现 final>1。
       故按路区分（见 `_ROUTE_META`）。
    2. **关键词相关性封顶 0.6**：关键字覆盖率在长章节上轻易饱和到 1.0，而向量分最高约 0.75，
       不封顶会让"整章长文本"系统性压过"语义最相关的片段"。
       （先试过 RRF 倒数排名融合：因路数少、各路质量差异大，几条弱路只要路内排第一就与
        向量 top1 同分——实测 rel 0.25 的技能包指南压过 rel 1.0 的真实成稿，故弃用。）

去重：同一 (filename, chapter) 保留最高分，`route` 合并为多路命中。

⚠️ 与 `search_reports` 的关系：`search_reports` 是**单路降级链**（保持向后兼容），
   本模块是**多路并发召回 + 重排**，供需要"质量优先"的场景（写章找同类写法）使用。
   两者都把"非报告来源"标注出来（`is_report_chunk=False`），不得作为报告引用。
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from rag.rag_search import (
    search_by_tags,
    search_knowledge_graph,
    search_qdrant,
    search_standards,
    search_wiki,
)

# 各召回路的来源权威度（0~1）；权威度参与重排，决定"同等相关时谁在前"
AUTHORITY: Dict[str, float] = {
    "standards": 1.00,        # 标准原文
    "skill_guide": 0.85,      # 技能包章节指南（固定条款，合规惯例）
    "local_folder": 0.75,     # 本地历史成稿（真实交付件）
    "qdrant_vector": 0.70,    # 向量库里的历史报告片段
    "qdrant_tags": 0.55,      # 仅按标签召回的片段（无 query 相关性）
    "llm_wiki_generated": 0.50,  # 自动生成的 wiki 页
    "knowledge_graph": 0.20,  # 图谱推断（非报告）
}

# 加权求和权重
W_RELEVANCE, W_MATCH, W_AUTHORITY, W_RECENCY = 0.55, 0.15, 0.15, 0.15
# 关键词类相关性的上限（见模块 docstring 校准第 2 条）
KEYWORD_REL_CAP = 0.6

_YEAR_RE = re.compile(r"(20[0-3]\d)")
_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{3,}|\d{2,}")


def _tokens(text: str) -> List[str]:
    return [t for t in _TOKEN_RE.findall(str(text or "")) if t]


def keyword_coverage(query: str, text: str) -> float:
    """查询词在文本中的覆盖率（0~1）。中文按 2-gram 粗切，英文/数字按整词。"""
    toks = _tokens(query)
    if not toks:
        return 0.0
    hay = str(text or "")
    hit = sum(1 for t in toks if t in hay)
    return hit / len(toks)


def _recency(filename: str, text: str = "") -> float:
    """时效分（0~1）：从文件名/正文抽 20xx 年份，最新年份记 1.0，越旧越低；抽不到给中性 0.5。"""
    years = [int(y) for y in _YEAR_RE.findall(str(filename or ""))]
    if not years:
        years = [int(y) for y in _YEAR_RE.findall(str(text or "")[:400])]
    if not years:
        return 0.5
    newest = max(years)
    # 以 2026 为基准，每早 1 年扣 0.1，最低 0.2
    return max(0.2, min(1.0, 1.0 - (2026 - newest) * 0.1))


def _match_score(item: Dict, tags: Optional[Dict]) -> float:
    """类型/地域匹配度：类别相符 1.0、无信息 0.4、不符 0.0。"""
    if not tags:
        return 0.5
    itags = item.get("tags") or {}
    wanted_cat = str(tags.get("institution_category") or "").strip()
    got_cat = str(itags.get("institution_category") or "").strip()
    if wanted_cat and got_cat:
        return 1.0 if wanted_cat == got_cat else 0.0
    wanted_type = str(tags.get("audit_type") or "").strip()
    got_type = str(itags.get("audit_type") or "").strip()
    if wanted_type and got_type:
        return 1.0 if wanted_type == got_type else 0.0
    return 0.4


# 各路的 `score` 语义不同，必须分开处理（否则会把"匹配分"当成"相关性"，
# 出现 final>1 的越界分：2026-09-20 实测本地库 score=3.0 被误当相关性）。
#   own_score_as_relevance=True  → 该路 score 本身就是 0~1 的相关性/置信度
#   gate_by_keyword=True         → 相关性为 0 时丢弃（防"不相关也召回"）
_ROUTE_META = {
    "qdrant_vector":   {"own_score_as_relevance": True,  "gate_by_keyword": False},
    "knowledge_graph": {"own_score_as_relevance": True,  "gate_by_keyword": False},
    "qdrant_tags":     {"own_score_as_relevance": False, "gate_by_keyword": True},
    "local_folder":    {"own_score_as_relevance": False, "gate_by_keyword": True},
    "skill_guide":     {"own_score_as_relevance": False, "gate_by_keyword": True},
    # 标准条文路：命中的是 Qdrant 向量分（0~1 相关性），与 qdrant_vector 同类——
    # 2026-09-20 P3-3 起本条路由真正产出结果（此前 AUTHORITY 里留了 1.00 却无人产出）。
    "standards":       {"own_score_as_relevance": True,  "gate_by_keyword": False},
    "llm_wiki_generated": {"own_score_as_relevance": False, "gate_by_keyword": True},
}


def _rank(raw: List[Dict], query: str, tags: Optional[Dict], route: str) -> List[Dict]:
    """给一路召回的原始结果补 route / 重排分量 / 统一 score（0~1）。"""
    meta = _ROUTE_META.get(route, {"own_score_as_relevance": False, "gate_by_keyword": True})
    out: List[Dict] = []
    for it in raw or []:
        text = str(it.get("text") or "")
        raw_score = it.get("score")
        cov = keyword_coverage(query, text)
        if meta["own_score_as_relevance"] and isinstance(raw_score, (int, float)):
            rel = float(raw_score)
        else:
            rel = min(cov, KEYWORD_REL_CAP)     # 关键词类封顶，防长文本饱和压过语义匹配
        if meta["gate_by_keyword"] and query and rel <= 0:
            continue                      # 与查询零相关 → 不要（历史事故：不相关也照返）
        # 匹配度：本地库的 score 是"机构类型/地域匹配分"（>0 表示匹配），据此加权
        if route == "local_folder" and isinstance(raw_score, (int, float)):
            match = 1.0 if raw_score > 0 else 0.4
        elif route == "knowledge_graph":
            match = 0.4                   # 图谱不参与类型匹配
        else:
            match = _match_score(it, tags)
        it = dict(it)
        it.setdefault("tags", {})
        it.setdefault("is_report_chunk", True)
        it["route"] = [route]
        it["rerank"] = {
            "relevance": round(rel, 4),
            "match": round(match, 4),
            "authority": AUTHORITY.get(route, 0.3),
            "recency": round(_recency(it.get("filename", ""), text), 4),
        }
        it["base_score"] = it.get("score")
        it["score"] = round(
            W_RELEVANCE * it["rerank"]["relevance"]
            + W_MATCH * it["rerank"]["match"]
            + W_AUTHORITY * it["rerank"]["authority"]
            + W_RECENCY * it["rerank"]["recency"], 4)
        out.append(it)
    return out


def smart_retrieve(query: str, tags: Optional[Dict] = None, top_k: int = 5,
                   chapter: str = "", reference_dir: Optional[str] = None,
                   include_standards: bool = False) -> Dict:
    """四路召回 + 重排序。返回形状兼容 `search_reports` 并额外带 route/rerank/routes。

    include_standards=True 时额外跑 R5 标准条文路（定额标准 / 技术规范），
    用于"查依据"型问题；默认关闭，见 R5 处说明。
    """
    tags = dict(tags or {})
    k = max(int(top_k) * 3, 10)
    pool: List[Dict] = []
    degraded: List[str] = []
    routes: Dict[str, int] = {}

    # R1 向量
    try:
        r1 = _rank(search_qdrant(query, tags, k), query, tags, "qdrant_vector")
        pool += r1
        routes["qdrant_vector"] = len(r1)
    except Exception as e:  # noqa: BLE001
        degraded.append("qdrant_vector")
        print(f"[smart] ⚠️ 向量路不可用：{e}")

    # R2 标签（无 query 相关性 → 必须过关键字闸，否则剔除以防"不相关也召回"）
    if tags:
        try:
            raw = search_by_tags(tags, k)
            raw = [it for it in raw if keyword_coverage(query, str(it.get("text") or "")) > 0]
            r2 = _rank(raw, query, tags, "qdrant_tags")
            pool += r2
            routes["qdrant_tags"] = len(r2)
        except Exception as e:  # noqa: BLE001
            degraded.append("qdrant_tags")
            print(f"[smart] ⚠️ 标签路不可用：{e}")

    # R3 关键字（本地成稿库 + 章节指南/wiki）
    try:
        from tools.energy_audit.reference_library import search_local_references
        lr = search_local_references(chapter or "", tags, top_k=k, reference_dir=reference_dir)
        r3a = _rank(lr.get("results") or [], query, tags, "local_folder")
        pool += r3a
        routes["local_folder"] = len(r3a)
    except Exception as e:  # noqa: BLE001
        degraded.append("local_folder")
        print(f"[smart] ⚠️ 本地成稿库不可用：{e}")
    try:
        wiki_raw = search_wiki(query, tags)
        r3b = []
        for it in wiki_raw[:k]:
            src = (it.get("tags") or {}).get("source") or "llm_wiki_generated"
            r3b += _rank([it], query, tags, src if src in AUTHORITY else "llm_wiki_generated")
        pool += r3b
        routes["wiki"] = len(r3b)
    except Exception as e:  # noqa: BLE001
        degraded.append("wiki")
        print(f"[smart] ⚠️ wiki 路不可用：{e}")

    # R4 权威/图谱（非报告，低权重；保留以便诊断类查询）
    try:
        r4 = _rank(search_knowledge_graph(query, tags), query, tags, "knowledge_graph")
        for it in r4:
            it["is_report_chunk"] = False
        pool += r4
        routes["knowledge_graph"] = len(r4)
    except Exception as e:  # noqa: BLE001
        degraded.append("knowledge_graph")
        print(f"[smart] ⚠️ 图谱路不可用：{e}")

    # R5 标准条文（定额标准 / 技术规范）—— 2026-09-20 P3-3
    #   默认**不开**：AUTHORITY["standards"]=1.00，混进来会系统性挤掉"同类成稿"路线，
    #   而写章时想看的恰恰是"别人怎么写的"而不是条文原文。要查依据时显式打开。
    if include_standards:
        try:
            r5 = _rank(search_standards(query, top_k=k), query, tags, "standards")
            pool += r5
            routes["standards"] = len(r5)
        except Exception as e:  # noqa: BLE001
            degraded.append("standards")
            print(f"[smart] ⚠️ 标准条文路不可用：{e}")

    # 去重：(filename, chapter) 保留最高分，命中路线合并（多路命中 = 更强证据）
    fused: Dict[Tuple[str, str], Dict] = {}
    for it in pool:
        key = (str(it.get("filename") or ""), str(it.get("chapter") or ""))
        cur = fused.get(key)
        if cur is None or it["score"] > cur["score"]:
            if cur is not None:
                it["route"] = sorted(set(cur.get("route") or []) | set(it.get("route") or []))
            it["route"] = sorted(it["route"])
            fused[key] = it
        else:
            cur["route"] = sorted(set(cur.get("route") or []) | set(it.get("route") or []))
    results = sorted(fused.values(), key=lambda x: -x["score"])[:max(1, int(top_k))]
    report_hits = [it for it in results if it.get("is_report_chunk", True)]
    note = ""
    if not results:
        note = ("四路召回均无命中（降级链：" + ("、".join(degraded) if degraded else "各层空") +
                "）。请检查 Qdrant / wiki / 本地成稿库，或如实说明无参考。")
    elif not report_hits:
        kinds = {str(it.get("kind") or "") for it in results}
        if "standard_clause" in kinds:
            note = ("命中的是标准/规范**条文原文**（非同类成稿）：可作依据引用，"
                    "但不得当 '机构同类报告' 仿写。")
        else:
            note = "未命中历史报告；命中的是知识图谱推断（非报告），不得作为报告引用来源。"
    return {
        "results": results,
        "source": "smart_multi_recall",
        "count": len(results),
        "routes": routes,
        "degraded": degraded,
        "is_report_retrieval": bool(report_hits),
        "note": note,
    }


if __name__ == "__main__":
    import json
    import sys

    q = sys.argv[1] if len(sys.argv) > 1 else "医院 单位建筑面积非供暖能耗 偏高"
    tg = {"institution_category": sys.argv[2]} if len(sys.argv) > 2 else None
    out = smart_retrieve(q, tg, top_k=5)
    print(f"query={q}  tags={tg}")
    print(f"routes={out['routes']}  degraded={out['degraded']}  "
          f"is_report_retrieval={out['is_report_retrieval']}")
    for it in out["results"]:
        print(f"  {it['score']:.3f} [{'+'.join(it['route'])}] {str(it.get('filename'))[:40]} | "
              f"{str(it.get('chapter'))[:26]} | rel={it['rerank']['relevance']}")
