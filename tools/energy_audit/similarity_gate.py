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

# ---------------------------------------------------------------- 查重白名单（2026-09-20 新增）
# 依据：energy-audit-style/references/rules.md《防抄三闸门·白名单》
# 白名单 = 各类报告中"本来就该逐字相同"的内容（标题、表格骨架、标准原文、固定条文）。
# 不排除它们，固定条文会把 LCS 拉到 65~70%，真问题被淹没（2026-09-20 A/B 实测）。
WHITELIST_LABELS = {
    "heading": "标题行",
    "table": "表格行（骨架/字段名）",
    "definition": "审计定义段（1.1 标准定义原文）",
    "standards_list": "审计依据清单行（1.6 法规/标准编号）",
    "metering_clause": "计量体系固定条文（4.1 GB/T 29149 六条）",
    "indicator_definition": "指标定义段（5.3 标准原文释义）",
    "appendix_fixed": "附录固定说明/固定表格",
}

_RE_STD_NO = re.compile(
    r"(GB\s?/?\s?T?\s?\d+|DB\s?37\s?/?\s?T?\s?\d+|JGJ\s?\d+|CJJ\s?/?\s?T?\s?\d+|"
    r"JS\s?/?\s?T\s?\d+|鲁事管发|国管局令|省政府令)"
)


def split_blocks(text: str) -> List[str]:
    """按空行切块（表格多行会合成一块，便于整体识别为白名单）。"""
    blocks, current = [], []
    for line in (text or "").splitlines():
        if line.strip():
            current.append(line)
        elif current:
            blocks.append("\n".join(current))
            current = []
    if current:
        blocks.append("\n".join(current))
    return blocks


def whitelist_label(block: str) -> Optional[str]:
    """判断一个块是否属于查重白名单；是则返回类别名。"""
    lines = [l.strip() for l in block.splitlines() if l.strip()]
    if not lines:
        return None
    total = len(lines)
    if sum(1 for l in lines if l.startswith("#")) * 2 > total:
        return "heading"
    if sum(1 for l in lines if l.startswith("|")) * 2 > total:
        return "table"
    text = block.strip()
    norm_len = len(normalize(text))
    if "公共机构能源审计是指" in text or "对公共机构的用能系统、设备的运行、管理及能源资源利用状况进行检验" in text:
        return "definition"
    list_lines = [l for l in lines if l[0] in "-·⚫●"]
    if list_lines and any(_RE_STD_NO.search(l) for l in list_lines):
        return "standards_list"
    if ("分户计量" in text or "分区计量" in text) and norm_len < 400:
        return "metering_clause"
    if "在统计报告期内" in text or ("计算公式如下" in text and "单位为" in text):
        return "indicator_definition"
    if any(k in text for k in ("空气质量判定", "折标准煤参考系数", "室内空气质量指标及要求")):
        return "appendix_fixed"
    return None


def filter_whitelist(text: str) -> tuple:
    """剔除白名单块，返回 (剩余文本, {类别: 块数})。"""
    kept: List[str] = []
    stats: Dict[str, int] = {}
    for block in split_blocks(text):
        label = whitelist_label(block)
        if label:
            stats[label] = stats.get(label, 0) + 1
        else:
            kept.append(block)
    return "\n\n".join(kept), stats


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
    use_whitelist: bool = True,
) -> Optional[Dict]:
    """生成稿与每份参考文本比对，返回查重报告；无参考或生成稿过短返回 None。

    use_whitelist=True（默认）时，先剔除"本来就该逐字相同"的白名单块
    （标题/表格骨架/标准原文/固定条文），避免固定条文把比率拉满造成误报。
    """
    whitelist_stats: Dict[str, int] = {}
    if use_whitelist:
        generated, whitelist_stats = filter_whitelist(generated)
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
        "whitelist": {
            "enabled": use_whitelist,
            "excluded_blocks": whitelist_stats,
            "excluded_total": sum(whitelist_stats.values()),
        },
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
    wl = (report.get("whitelist") or {}).get("excluded_blocks") or {}
    wl_text = ""
    if wl:
        detail = "、".join(f"{WHITELIST_LABELS.get(k, k)} {v}" for k, v in wl.items())
        wl_text = f"（已豁免白名单 {sum(wl.values())} 块：{detail}）"
    if report["passed"]:
        return f"查重通过{wl_text}"
    return (
        f"疑似复述：最长连续相同 {report['max_match_len']} 字，"
        f"LCS 占比 {report['lcs_ratio']:.2%}，6-gram 重合 {report['ngram_overlap']:.2%}{wl_text}"
    )
