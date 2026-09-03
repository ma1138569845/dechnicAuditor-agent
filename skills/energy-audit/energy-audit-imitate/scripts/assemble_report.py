#!/usr/bin/env python3
"""Assemble agent-written energy-audit chapters into a formatted Word file.

Reads a JSON spec and writes a .docx via WordReportBuilder (imitate mode).
Does not call the scripted imitate pipeline or the LLM.

Usage:
  python scripts/assemble_report.py spec.json reports/unit能源审计报告.docx
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

CHAPTER_KEYS = [f"第{i}章" for i in range(1, 9)]
AUDIT_TYPES = ("公共机构", "公共建筑", "工业企业")


def load_spec(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("spec must be a JSON object")
    return data


def resolve_unit_name(spec: Dict[str, Any]) -> str:
    """优先取 unit_name；否则从 project_name 去掉「能源审计报告/能源审计」后缀。"""
    unit_name = str(spec.get("unit_name") or "").strip()
    if unit_name:
        return unit_name
    project_name = str(spec.get("project_name") or "").strip()
    for suffix in ("能源审计报告", "能源审计"):
        if project_name.endswith(suffix):
            return project_name[: -len(suffix)].strip()
    return project_name


def normalize_chapters(raw: Any) -> Dict[str, str]:
    if not isinstance(raw, dict) or not raw:
        raise ValueError("imitated_chapters must be a non-empty object keyed by 第1章…第8章")
    chapters: Dict[str, str] = {}
    missing: List[str] = []
    for key in CHAPTER_KEYS:
        value = raw.get(key)
        if isinstance(value, dict):
            text = str(value.get("text") or "").strip()
        else:
            text = str(value or "").strip()
        if not text:
            missing.append(key)
        else:
            chapters[key] = text
    if missing:
        raise ValueError("missing chapter text: " + "、".join(missing))
    return chapters


def build_report_data(spec: Dict[str, Any]) -> Dict[str, Any]:
    project_name = str(spec.get("project_name") or "").strip()
    if not project_name:
        raise ValueError("project_name is required")
    audit_type = str(spec.get("audit_type") or "公共机构").strip() or "公共机构"
    if audit_type not in AUDIT_TYPES:
        raise ValueError(f"audit_type must be one of {', '.join(AUDIT_TYPES)}")
    chapters = normalize_chapters(spec.get("imitated_chapters"))
    cover = spec.get("cover") if isinstance(spec.get("cover"), dict) else {}
    title = str(cover.get("title") or f"{project_name}能源审计报告").strip()
    return {
        "project_name": project_name,
        "unit_name": resolve_unit_name(spec),
        "audit_type": audit_type,
        "generation_mode": "imitate",
        "cover": {
            "title": title,
            "audit_organization": str(cover.get("audit_organization") or "").strip(),
            "report_date": str(cover.get("report_date") or "").strip(),
        },
        "audit_info_tables": spec.get("audit_info_tables") if isinstance(spec.get("audit_info_tables"), dict) else {},
        "chart_data": spec.get("chart_data") if isinstance(spec.get("chart_data"), dict) else {},
        "imitated_chapters": chapters,
    }


def assemble(spec: Dict[str, Any], output_path: Path) -> Path:
    from tools.energy_audit.report_generator import ReportGenerator

    report_data = build_report_data(spec)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    gen = ReportGenerator(report_data["audit_type"])
    gen.set_report_data(report_data)
    gen.generate_word(str(output_path))

    # 落盘后注入 DrawingML 单位全称水印（规范：禁止 VML textpath）
    import importlib.util as _ilu

    _wm_script = Path(__file__).resolve().parent / "add_watermark.py"
    _wm_spec = _ilu.spec_from_file_location("add_watermark", _wm_script)
    assert _wm_spec and _wm_spec.loader
    _wm_mod = _ilu.module_from_spec(_wm_spec)
    _wm_spec.loader.exec_module(_wm_mod)
    _wm_mod.add_unit_name_watermark(str(output_path), report_data["unit_name"])
    return output_path


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assemble imitated energy-audit chapters into Word")
    parser.add_argument("spec", help="JSON spec with project_name, audit_type, imitated_chapters")
    parser.add_argument("output", help="Output .docx path")
    args = parser.parse_args(argv)
    spec_path = Path(args.spec)
    output_path = Path(args.output)
    if not spec_path.is_file():
        print(f"spec not found: {spec_path}", file=sys.stderr)
        return 2
    try:
        spec = load_spec(spec_path)
        written = assemble(spec, output_path)
    except Exception as exc:
        print(f"assemble failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "file_path": str(written)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
