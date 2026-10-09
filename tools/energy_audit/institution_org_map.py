# -*- coding: utf-8 -*-
"""机构类型 → (org_type, action_desc, special_note) 唯一映射（2026-10-08 收口）。

唯一权威：skills/energy-audit/ea-calculation/references/chapter5-templates.md
§5.3.1「机构类型映射」表。本模块是该表的代码副本，供 chapter5_agent.py 取用；
两侧一致性由 ea-validation/scripts/verify_org_map.py 静态校验（不一致即报错）。
"""
from __future__ import annotations

ORG_MAP: dict[str, tuple[str, str, str]] = {
    "medical":    ("医疗机构", "从事疾病诊断、治疗活动",
                   "大型医疗设备、数据中心、厨房炊事、洗衣房"),
    "service":    ("政务服务中心", "日常办公", "数据中心、厨房炊事"),
    "venue":      ("场馆机构", "运行", "数据中心、厨房炊事、专业设备"),
    "education":  ("教育机构", "运行", "数据中心、实验室、厨房炊事"),
    "government": ("党政机关", "日常办公", "数据中心、厨房炊事、专业用途设备"),
    "other":      ("公共机构", "运行", "数据中心、厨房炊事"),
}

_DEFAULT = "government"


def _row(institution_type: str) -> tuple[str, str, str]:
    return ORG_MAP.get((institution_type or "").strip(), ORG_MAP[_DEFAULT])


def org_type_for(institution_type: str) -> str:
    return _row(institution_type)[0]


def action_desc_for(institution_type: str) -> str:
    return _row(institution_type)[1]


def special_note_for(institution_type: str) -> str:
    return _row(institution_type)[2]
