"""防抄查重闸门：生成稿 vs 参考报告文本的句子级相似度检查。

规则依据 `energy-audit-style/references/anti-copy-gate.md`（三闸门之第 3 闸）：
- lcs_ratio：最长公共子串总匹配长度 / 生成文本长度，≥ 0.15 报疑似复述；
- ngram_overlap：6-gram 交集占比，≥ 0.25 报短语级雷同（同构改写也逃不掉）；
- 连续 ≥12 个可对比字符完全相同 → 直接违规（句法层红线）。

归一化：只取汉字/字母/数字序列（去掉标点与空白），避免"标点相同"噪声。
短文本（<50 字符）跳过——固定条款/定义段短句不做机械判定，由 editor 人工核。
"""
from __future__ import annotations

import difflib
import re
from typing import Dict, List, Optional, Sequence

# 阈值（与 anti-copy-gate.md 保持一致）
LCS_RATIO_THRESHOLD = 0.15
NGRAM_OVERLAP_THRESHOLD = 0.25
MIN_CONTIGUOUS = 12  # 连续相同字符红线
MIN_TEXT_LEN = 50     # 过短文本不查（固定短条款，人工核）
NGRAM_N = 6
REPORT_MATCH_LEN = 8  # violations 里收录的最短匹配块

_KEEP_RE = re.compile(r"[0-9A-Za-z\u4e00-\u9fff]+")


def normalize(text: str) -> str:
    """提取汉字/字母/数字序列，去掉标点与空白。"""
    return "".join(_KEEP_RE.findall(text or ""))


def _ngrams(text: str, n: int = NGRAM_N) -> set:
    if len(text) < n:
        return set()
    return {text[i : i + n] for i in range(len(text) - n + 1)}


def _lcs_blocks(a: str, b: str, min_len: int = REPORT_MATCH_LEN):
    """返回 (总匹配长度, 最长匹配块长, 匹配块列表[(a_pos, b_pos, len)])。"""
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    blocks = [blk for blk in sm.get_matching_blocks() if blk.size >= min_len]
    total = sum(blk.size for blk in blocks)
    longest = max((blk.size for blk in blocks), default=0)
    return total, longest, blocks


def check_similarity(
    generated: str,
    references: Sequence[str],
    *,
    lcs_ratio_threshold: float = LCS_RATIO_THRESHOLD,
    ngram_overlap_threshold: float = NGRAM_OVERLAP_THRESHOLD,
    min_text_len: int = MIN_TEXT_LEN,
) -> Optional[Dict]:
    """生成稿与每份参考文本比对，返回查重报告；无参考或生成稿过短返回 None。"""
    g = normalize(generated)
    if not g or len(g) < min_text_len:
        return None
    refs = [(i, normalize(r)) for i, r in enumerate(references) if normalize(r)]
    if not refs:
        return None

    worst: Dict = {
        "passed": True,
        "lcs_ratio": 0.0,
        "max_match_len": 0,
        "ngram_overlap": 0.0,
        "violations": [],
        "reference_count": len(refs),
    }
    g_ngrams = _ngrams(g)
    for idx, r in refs:
        total, longest, blocks = _lcs_blocks(g, r)
        lcs_ratio = total / len(g) if total else 0.0
        overlap = len(g_ngrams & _ngrams(r)) / len(g_ngrams) if g_ngrams else 0.0
        worst["lcs_ratio"] = max(worst["lcs_ratio"], lcs_ratio)
        worst["max_match_len"] = max(worst["max_match_len"], longest)
        worst["ngram_overlap"] = max(worst["ngram_overlap"], overlap)
        for ap, _bp, size in blocks[:5]:
            worst["violations"].append({
                "ref_index": idx,
                "matched": g[ap : ap + size],
                "length": size,
                "kind": "lcs",
            })
        if len(worst["violations"]) >= 5:
            break

    worst["passed"] = not (
        worst["max_match_len"] >= MIN_CONTIGUOUS
        or worst["lcs_ratio"] >= lcs_ratio_threshold
        or worst["ngram_overlap"] >= ngram_overlap_threshold
    )
    return worst


def format_flags(report: Optional[Dict]) -> str:
    """把查重报告转成给调用方/editor 看的一行中文结论。"""
    if report is None:
        return "无参考文本或生成稿过短，跳过查重"
    if report["passed"]:
        return "查重通过"
    return (
        f"疑似复述：最长连续相同 {report['max_match_len']} 字，"
        f"LCS 占比 {report['lcs_ratio']:.2%}，6-gram 重合 {report['ngram_overlap']:.2%}"
    )
