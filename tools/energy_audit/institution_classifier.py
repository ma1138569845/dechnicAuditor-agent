"""
Shared institution classifier for energy audit reports.

Consolidates classification logic previously duplicated across
energy_audit_importer.py and ingest_reports.py.  Supports both
filename-only and filename+content matching.

Usage:
    from tools.energy_audit.institution_classifier import classify_institution
    category, specific_type = classify_institution(filename, text)
"""

from __future__ import annotations

from typing import Tuple

# ── category → specific-type mapping ────────────────────────────

_MEDICAL_KEYWORDS: list[Tuple[str, str]] = [
    ("卫生健康局", "卫生健康局"),
    ("卫健委", "卫健委"),
    ("妇幼", "妇幼保健"),
    ("疾控", "疾控中心"),
    ("疾病预防", "疾控中心"),
    ("中心医院", "中心医院"),
    ("保健院", "妇幼保健"),
    ("人民医院", "医院"),
    ("医院", "医院"),
]

_EDUCATION_KEYWORDS: list[Tuple[str, str]] = [
    ("技师学院", "技师学院"),
    ("大学", "大学"),
    ("实验中学", "实验中学"),
    ("海洋工程学校", "职业学校"),
    ("学院", "职业学院"),
    ("中学", "中学"),
    ("高中", "中学"),
    ("学校", "中学"),
    ("三中", "中学"),
    ("一中", "中学"),
    ("二中", "中学"),
]

_GOVERNMENT_KEYWORDS: list[Tuple[str, str]] = [
    ("财政局", "财政局"),
    ("海洋发展局", "海洋局"),
    ("交通运输局", "交通局"),
    ("市场监管局", "市场监管局"),
    ("人民法院", "法院"),
    ("人民检察院", "检察院"),
    ("纪委监委", "纪委监委"),
    ("自然资源局", "自然资源局"),
    ("生态环境局", "生态环境局"),
    ("生态环境厅", "生态环境厅"),
    ("科技厅", "科技厅"),
    ("司法厅", "司法厅"),
    ("人社厅", "人社厅"),
    ("人社", "人社厅"),
    ("信访局", "信访局"),
    ("科协", "科协"),
    ("团委", "团委"),
    ("团省委", "共青团"),
    ("党校", "党校"),
    ("机关事务", "机关事务中心"),
    ("监狱", "监狱局"),
    ("贸促会", "贸促会"),
    ("法院", "法院"),
]

_VENUE_KEYWORDS: list[Tuple[str, str]] = [
    ("图书馆", "图书馆"),
    ("干部活动", "老干部活动中心"),
]

_SPORTS_KEYWORDS: list[Tuple[str, str]] = [
    ("体育训练", "体育训练中心"),
    ("体育", "体育训练中心"),
]

# Ordered search: first match wins within each category
_CATEGORY_RULES: list[Tuple[str, list[Tuple[str, str]]]] = [
    ("医疗", _MEDICAL_KEYWORDS),
    ("教育", _EDUCATION_KEYWORDS),
    ("场馆机构", _VENUE_KEYWORDS),
    ("体育", _SPORTS_KEYWORDS),
    ("党政机关", _GOVERNMENT_KEYWORDS),
]


def classify_institution(
    filename: str, text: str = ""
) -> Tuple[str, str]:
    """Classify an energy audit report by institution category and specific type.

    Args:
        filename: The report filename (used for keyword matching).
        text: Optional first ~2000 chars of document content for
              supplementary matching.

    Returns:
        (institution_category, specific_type) — e.g. ("医疗", "医院").
        Falls back to ("未分类", "其他") when no match is found.
    """
    # Build search corpus: filename + content head
    corpus = filename + text[:2000]

    for category, rules in _CATEGORY_RULES:
        for keyword, specific_type in rules:
            if keyword in corpus:
                return (category, specific_type)

    return ("未分类", "其他")
