#!/usr/bin/env python3
"""Build the pre-authoring photo fact catalog.

The catalog is deliberately advisory: it gives the report author the
database-backed purpose of each distinct physical photo plus any optional
visual observations. A missing visual service leaves the photo usable with
only neutral, data-bound caption facts.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional


CATALOG_FILENAME = "photo_catalog.json"
VISUAL_CACHE_FILENAME = "photo_visual_cache.json"
VISUAL_CACHE_VERSION = 1
MIN_VISUAL_CONFIDENCE = 0.80

CHAPTER_BY_CATEGORY = {
    "单位整体外观": "第2章",
    "建筑外观": "第2章",
    "管理文件/荣誉": "第3章",
    "计量器具": "第4章",
    "缴费发票": "第5章",
    "节能改造示意": "第7章",
}

METER_LABELS = {
    1: "电表",
    2: "水表",
    3: "燃气表",
    4: "热表",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _ids(value: Any) -> List[str]:
    if isinstance(value, (list, tuple, set)):
        raw = " ".join(str(item or "") for item in value)
    else:
        raw = str(value or "")
    return re.findall(r"\d+", raw)


def _sha256(path: Path) -> str:
    if not path.is_file():
        return ""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


def _identity(image: Dict[str, Any]) -> str:
    file_id = _text(image.get("file_id"))
    if file_id:
        return f"file_id:{file_id}"
    return f"path:{Path(_text(image.get('path'))).resolve()}"


def _chapter_for(category: str) -> str:
    if category in CHAPTER_BY_CATEGORY:
        return CHAPTER_BY_CATEGORY[category]
    if category in {
        "制冷设备", "照明设备", "办公设备", "信息机房", "医疗设备",
        "其他用电设备", "特殊设备", "变压器/配电", "水泵/水箱", "厨房设备",
    }:
        return "第6章"
    return ""


def _binding(ref: str, label: str, chapter: str, kind: str) -> Dict[str, str]:
    return {
        "ref": ref,
        "label": _text(label),
        "chapter": chapter,
        "kind": kind,
    }


def _add_binding(candidate: Dict[str, Any], binding: Dict[str, str]) -> None:
    key = (
        binding.get("ref", ""),
        binding.get("label", ""),
        binding.get("chapter", ""),
    )
    existing = {
        (item.get("ref", ""), item.get("label", ""), item.get("chapter", ""))
        for item in candidate["bindings"]
    }
    if key not in existing:
        candidate["bindings"].append(binding)


def _candidate_from_rows(identity: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    first = rows[0]
    path = Path(_text(first.get("path"))).resolve()
    categories = sorted({_text(row.get("category")) for row in rows if row.get("category")})
    captions = sorted({_text(row.get("caption")) for row in rows if row.get("caption")})
    buildings = sorted({
        _text(row.get("building_name"))
        for row in rows
        if row.get("building_name")
    })
    file_id = _text(first.get("file_id"))
    return {
        "candidate_id": identity,
        "file_id": file_id,
        "source_path": str(path),
        "source_sha256": _sha256(path),
        "category": categories[0] if categories else "",
        "categories": categories,
        "buildings": buildings,
        "captions": captions,
        "bindings": [],
        "content_aliases": [],
        "visual": {
            "status": "unverified",
            "reason": "未启用视觉事实提取",
            "observed": {},
        },
        "suggested_caption": "",
    }


def _candidate_index(candidates: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for candidate in candidates:
        file_id = _text(candidate.get("file_id"))
        if file_id:
            index[f"file_id:{file_id}"] = candidate
            index[f"id:{file_id}"] = candidate
        path = _text(candidate.get("source_path"))
        if path:
            for path_key in {
                path,
                os.path.normcase(os.path.abspath(path)),
            }:
                index[f"path:{path_key}"] = candidate
    return index


def _attach_data_bindings(
    data: Dict[str, Any],
    candidates: List[Dict[str, Any]],
) -> None:
    index = _candidate_index(candidates)

    for candidate in candidates:
        for category in candidate.get("categories") or []:
            chapter = _chapter_for(category)
            if category in {"单位整体外观", "建筑外观"}:
                for building in candidate.get("buildings") or []:
                    _add_binding(
                        candidate,
                        _binding("images[].building_name", building, "第2章", "building"),
                    )
            elif chapter:
                _add_binding(
                    candidate,
                    _binding("images[].category", category, chapter, "category"),
                )

    for equipment in data.get("equipment") or []:
        label = _text(equipment.get("name"))
        for file_id in _ids(equipment.get("img_ids")):
            candidate = index.get(f"file_id:{file_id}")
            if candidate and label:
                _add_binding(
                    candidate,
                    _binding("equipment[].img_ids", label, "第6章", "equipment"),
                )

    for meter in data.get("energy_meter") or []:
        try:
            data_type = int(meter.get("data_type"))
        except (TypeError, ValueError):
            data_type = 0
        label = METER_LABELS.get(data_type, "计量器具")
        for file_id in _ids(meter.get("device_img")):
            candidate = index.get(f"file_id:{file_id}")
            if candidate:
                _add_binding(
                    candidate,
                    _binding("energy_meter[].device_img", label, "第4章", "metering"),
                )

    for saving in data.get("energy_saving") or []:
        award_title = _text(saving.get("award_name"))
        award_keys = [f"file_id:{file_id}" for file_id in _ids(saving.get("award_certificate"))]
        award_keys.extend(
            f"path:{os.path.normcase(os.path.abspath(_text(path)))}"
            for path in (saving.get("award_certificate_images") or [])
            if _text(path)
        )
        for key in award_keys:
            candidate = index.get(key)
            if candidate and award_title:
                _add_binding(
                    candidate,
                    _binding(
                        "energy_saving[].award_certificate",
                        award_title,
                        "第3章",
                        "award",
                    ),
                )

        management_keys = [
            f"file_id:{file_id}"
            for file_id in _ids(saving.get("management_files"))
        ]
        management_keys.extend(
            f"path:{os.path.normcase(os.path.abspath(_text(path)))}"
            for path in (saving.get("management_file_images") or [])
            if _text(path)
        )
        for key in management_keys:
            candidate = index.get(key)
            if candidate:
                _add_binding(
                    candidate,
                    _binding(
                        "energy_saving[].management_files",
                        "能源管理制度文件",
                        "第3章",
                        "management",
                    ),
                )


def _suggested_caption(candidate: Dict[str, Any], unit_short: str) -> str:
    bindings = candidate.get("bindings") or []
    for kind, prefix in (("award", "图3.N"), ("equipment", "图6.N")):
        for binding in bindings:
            if binding.get("kind") == kind and binding.get("label"):
                return f"{prefix} {binding['label']}"
    for binding in bindings:
        if binding.get("kind") == "building" and binding.get("label"):
            return f"图2.N {binding['label']}总体外观"
    categories = candidate.get("categories") or []
    if "单位整体外观" in categories:
        return f"图2.N {unit_short}单位整体外观"
    if "计量器具" in categories:
        return "图4.N 计量器具照片"
    if categories:
        return categories[0]
    return "照片"


def _visual_status(observed: Dict[str, Any]) -> str:
    try:
        confidence = float(observed.get("confidence"))
    except (TypeError, ValueError):
        return "review"
    return "pass" if confidence >= MIN_VISUAL_CONFIDENCE else "review"


def _normalize_visual_result(result: Dict[str, Any]) -> Dict[str, Any]:
    result = result or {}
    status = _text(result.get("status"))
    observed = result.get("observed")
    if status in {"pass", "review", "unverified"} and isinstance(observed, dict):
        return {
            "status": status,
            "reason": _text(result.get("reason")),
            "observed": observed,
            "model": _text(result.get("model")),
        }
    return {
        "status": _visual_status(result),
        "reason": "",
        "observed": result,
        "model": _text(result.get("model")),
    }


def _apply_visuals(
    candidates: List[Dict[str, Any]],
    visualizer: Optional[Callable[[str, str], Dict[str, Any]]],
    cache: Dict[str, Any],
) -> bool:
    dirty = False
    by_hash: Dict[str, List[Dict[str, Any]]] = {}
    for candidate in candidates:
        digest = _text(candidate.get("source_sha256"))
        key = f"sha256:{digest}" if digest else candidate["candidate_id"]
        by_hash.setdefault(key, []).append(candidate)

    for grouped in by_hash.values():
        first = grouped[0]
        digest = _text(first.get("source_sha256"))
        cached = cache.get(digest) if digest else None
        if (
            isinstance(cached, dict)
            and cached.get("status") in {"pass", "review"}
            and isinstance(cached.get("observed"), dict)
        ):
            visual = cached
        elif visualizer is None:
            continue
        else:
            context = "；".join(
                binding.get("label", "")
                for binding in first.get("bindings") or []
                if binding.get("label")
            )
            try:
                visual = _normalize_visual_result(
                    visualizer(first["source_path"], context)
                )
                if digest and visual["status"] in {"pass", "review"}:
                    cache[digest] = json.loads(
                        json.dumps(visual, ensure_ascii=False)
                    )
                    dirty = True
            except Exception as exc:  # noqa: BLE001
                visual = {
                    "status": "unverified",
                    "reason": f"视觉事实提取不可用：{exc}",
                    "observed": {},
                }
        for candidate in grouped:
            candidate["visual"] = json.loads(json.dumps(visual, ensure_ascii=False))
    return dirty


def _load_visual_cache(project_dir: Path) -> Dict[str, Any]:
    path = project_dir / VISUAL_CACHE_FILENAME
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    observations = data.get("observations") if isinstance(data, dict) else {}
    return observations if isinstance(observations, dict) else {}


def _write_visual_cache(project_dir: Path, observations: Dict[str, Any]) -> None:
    path = project_dir / VISUAL_CACHE_FILENAME
    path.write_text(
        json.dumps({
            "version": VISUAL_CACHE_VERSION,
            "observations": observations,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_photo_catalog(
    data: Dict[str, Any],
    project_dir: str | Path,
    visualizer: Optional[Callable[[str, str], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build a deterministic photo catalog from project data."""
    project_root = Path(project_dir)
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for image in data.get("images") or []:
        if not isinstance(image, dict) or not _text(image.get("path")):
            continue
        grouped.setdefault(_identity(image), []).append(image)

    candidates = [
        _candidate_from_rows(identity, rows)
        for identity, rows in grouped.items()
    ]
    _attach_data_bindings(data, candidates)

    by_hash: Dict[str, List[Dict[str, Any]]] = {}
    for candidate in candidates:
        digest = _text(candidate.get("source_sha256"))
        if digest:
            by_hash.setdefault(digest, []).append(candidate)
    for grouped_candidates in by_hash.values():
        file_ids = [
            _text(candidate.get("file_id"))
            for candidate in grouped_candidates
            if candidate.get("file_id")
        ]
        for candidate in grouped_candidates:
            own = _text(candidate.get("file_id"))
            candidate["content_aliases"] = [
                file_id for file_id in file_ids if file_id != own
            ]

    visual_cache = _load_visual_cache(project_root)
    cache_dirty = _apply_visuals(candidates, visualizer, visual_cache)
    if cache_dirty:
        _write_visual_cache(project_root, visual_cache)
    unit_short = _text((data.get("base") or {}).get("unit_short"))
    unit_short = unit_short or _text((data.get("base") or {}).get("unit_name")) or "单位"
    for candidate in candidates:
        candidate["suggested_caption"] = _suggested_caption(candidate, unit_short)

    aliases = [candidate for candidate in candidates if candidate.get("content_aliases")]
    warnings = []
    if aliases:
        warnings.append(
            "存在不同 file_id 但图片内容完全相同的别名照片；已共享视觉事实，"
            "但每个 file_id 仍保留独立来源记录。"
        )
    return {
        "version": 1,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "candidates": candidates,
        "warnings": warnings,
    }


def write_photo_catalog(project_dir: str | Path, catalog: Dict[str, Any]) -> str:
    path = Path(project_dir) / CATALOG_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(path)
