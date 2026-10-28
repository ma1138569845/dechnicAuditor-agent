"""Read-only health and governance audit for the local skill library.

This module deliberately contains no mutation path. Every input is a read-only
snapshot; recommendations never archive, delete, rewrite, repair, or retune a
skill, proposal, Curator state, config value, or session record.
"""

from __future__ import annotations

import json
import logging
import math
import statistics
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RECOMMENDATION_STATUSES = ("KEEP", "REVIEW", "STALE", "BROKEN")
_BROKEN = "BROKEN"
_KEEP = "KEEP"
_REVIEW = "REVIEW"
_STALE = "STALE"
_ONE_DAY_SECONDS = 86_400
logger = logging.getLogger(__name__)


def curator_archive_after_days() -> int:
    """Read the Curator threshold without importing its stateful runtime module."""
    try:
        from hermes_constants import get_config_path

        path = get_config_path()
        if not path.exists():
            return 30
        import yaml

        config = yaml.safe_load(path.read_text(encoding="utf-8-sig")) or {}
        curator = config.get("curator") if isinstance(config, Mapping) else {}
        value = int(curator.get("archive_after_days", 30)) if isinstance(curator, Mapping) else 30
        return value if value >= 1 else 30
    except Exception:
        logger.warning("skill health: curator threshold read failed", exc_info=True)
        return 30


def load_usage() -> dict[str, dict[str, Any]]:
    """Thin read-only usage snapshot adapter."""
    from tools.skill_usage import load_usage as _load_usage

    return _load_usage()


def _skill_catalog_snapshot() -> tuple[list[dict[str, Any]], list[Path], set[str]]:
    """Parsed catalog, raw discovery paths, and raw paths that could not be parsed."""
    from agent.skill_utils import (
        TIER_LOCAL,
        TIER_PROJECT,
        get_skill_search_roots,
        iter_project_skill_files,
        iter_skill_index_files,
        parse_frontmatter,
        resolve_skill_catalog,
    )
    from hermes_constants import get_hermes_home

    active = get_hermes_home() / "skills"
    roots = [
        (tier, root)
        for tier, root in get_skill_search_roots(active)
        if tier != TIER_LOCAL or root.exists()
    ]
    raw_paths: list[Path] = []
    scanned: list[dict[str, Any]] = []
    unreadable: set[str] = set()
    for tier, root in roots:
        iterator = (
            iter_project_skill_files(root)
            if tier == TIER_PROJECT
            else iter_skill_index_files(root, "SKILL.md")
        )
        for path in iterator:
            skill_md = Path(path)
            raw_paths.append(skill_md)
            try:
                frontmatter, _body = parse_frontmatter(
                    skill_md.read_text(encoding="utf-8-sig")[:4000]
                )
            except (OSError, UnicodeError, ValueError):
                unreadable.add(_path_key(skill_md))
                continue
            scanned.append(
                {
                    "name": str(frontmatter.get("name") or skill_md.parent.name),
                    "description": str(frontmatter.get("description") or ""),
                    "category": "",
                    "tier": tier,
                    "root": root,
                    "path": skill_md,
                }
            )
    catalog = resolve_skill_catalog(scanned)
    return catalog, raw_paths, unreadable


def _cron_referenced_skill_names() -> set[str]:
    """Read jobs.json without importing the cron runtime's write-capable module."""
    try:
        from agent.skill_utils import normalize_skill_lookup_name
        from hermes_constants import get_hermes_home

        path = get_hermes_home() / "cron" / "jobs.json"
        if not path.exists():
            return set()
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        jobs = data.get("jobs", []) if isinstance(data, Mapping) else data
        if not isinstance(jobs, list):
            return set()
        names: set[str] = set()
        for job in jobs:
            if not isinstance(job, Mapping):
                continue
            skills = job.get("skills")
            if isinstance(skills, str):
                skills = [skills]
            elif not isinstance(skills, list):
                skills = []
            values = [job.get("skill"), *skills]
            for value in values:
                if not isinstance(value, str) or not value.strip():
                    continue
                name = normalize_skill_lookup_name(value) or value
                names.add(name.strip().lstrip("/"))
        return names
    except Exception:
        logger.warning("skill health: cron reference read failed", exc_info=True)
        return set()


def _hub_installed_skill_names() -> set[str]:
    try:
        from tools.skill_usage import _read_hub_installed_names

        return set(_read_hub_installed_names())
    except Exception:
        logger.warning("skill health: hub provenance read failed", exc_info=True)
        return set()


def _external_skill_names() -> set[str]:
    try:
        from tools.skill_usage import _external_skill_names as _names

        return set(_names())
    except Exception:
        logger.warning("skill health: external provenance read failed", exc_info=True)
        return set()


def _modified_skill_names() -> set[str]:
    try:
        from tools.skills_sync_bundled_ops import list_user_modified_bundled_skills

        return {str(item["name"]) for item in list_user_modified_bundled_skills()}
    except Exception:
        logger.warning("skill health: modified-skill read failed", exc_info=True)
        return set()


def _archived_skill_names() -> set[str]:
    try:
        from tools.skill_usage import list_archived_skill_names

        return set(list_archived_skill_names())
    except Exception:
        logger.warning("skill health: archive listing failed", exc_info=True)
        return set()


def _ledger_entries() -> list[dict[str, Any]]:
    try:
        from tools.skill_ledger import list_entries

        return list_entries(limit=5000)
    except Exception:
        logger.warning("skill health: ledger read failed", exc_info=True)
        return []


def _skill_learning_config():
    from tools.skill_learning_config import get_skill_learning_config

    raw: Mapping[str, Any] = {}
    try:
        from hermes_constants import get_config_path

        path = get_config_path()
        if path.exists():
            import yaml

            raw = yaml.safe_load(path.read_text(encoding="utf-8-sig")) or {}
    except Exception:
        logger.warning("skill health: learning config read failed", exc_info=True)
        raw = {}
    return get_skill_learning_config(raw)


def _proposal_records(config: Any = None) -> list[dict[str, Any]]:
    if config is None:
        return []
    try:
        from tools.skill_proposals import read_skill_proposal_records

        return read_skill_proposal_records(
            status="all", update_conflicts=False, config=config
        )
    except Exception:
        logger.warning("skill health: proposal read failed", exc_info=True)
        return []


def _proposal_queue(now: float, config: Any = None) -> dict[str, Any]:
    if config is None:
        return {"broken_count": 0}
    try:
        from tools.skill_proposals import get_skill_proposal_queue_state

        return get_skill_proposal_queue_state(now=now, config=config)
    except Exception:
        logger.warning("skill health: proposal queue read failed", exc_info=True)
        return {"broken_count": 0}


def _path_key(value: Any) -> str:
    try:
        return str(Path(str(value)).expanduser().resolve(strict=False))
    except (OSError, TypeError, ValueError):
        return str(value or "")


def _timestamp(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.timestamp()


def _activity_timestamp(record: Mapping[str, Any] | None) -> float | None:
    if not isinstance(record, Mapping):
        return None
    values = [
        parsed
        for key in ("last_used_at", "last_viewed_at", "last_patched_at")
        if (parsed := _timestamp(record.get(key))) is not None
    ]
    return max(values) if values else None


def _created_timestamp(record: Mapping[str, Any] | None, path: Path) -> float | None:
    if isinstance(record, Mapping):
        for key in ("created_at", "first_seen_at"):
            if (parsed := _timestamp(record.get(key))) is not None:
                return parsed
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _reason_order(reason: str) -> int:
    preferred = {
        "unreadable_skill": 0,
        "duplicate_discovery_path": 1,
        "pinned": 2,
        "cron_referenced": 3,
        "user_owned": 4,
        "external_skill": 5,
        "hub_skill": 6,
        "modified_skill": 7,
        "recent_usage": 8,
        "usage_evidence_incomplete": 9,
        "too_new": 10,
        "idle_after_threshold": 11,
        "insufficient_activity_evidence": 12,
    }
    return preferred.get(reason, 99)


def _recommendation(
    name: str,
    *,
    path: Path,
    broken_reasons: Sequence[str],
    record: Mapping[str, Any] | None,
    usage_complete: bool,
    now: float,
    window_days: int,
    archive_days: int,
    cron_names: set[str],
    hub_names: set[str],
    external_names: set[str],
    modified_names: set[str],
) -> tuple[str, list[str]]:
    if broken_reasons:
        return _BROKEN, sorted(set(broken_reasons), key=_reason_order)

    keep_reasons: list[str] = []
    if record and record.get("pinned") is True:
        keep_reasons.append("pinned")
    if name in cron_names:
        keep_reasons.append("cron_referenced")
    if record and record.get("created_by") != "agent":
        keep_reasons.append("user_owned")
    if name in external_names:
        keep_reasons.append("external_skill")
    if name in hub_names:
        keep_reasons.append("hub_skill")
    if name in modified_names:
        keep_reasons.append("modified_skill")
    recent = _activity_timestamp(record)
    if recent is not None and now - recent <= window_days * _ONE_DAY_SECONDS:
        keep_reasons.append("recent_usage")
    if keep_reasons:
        return _KEEP, sorted(set(keep_reasons), key=_reason_order)

    if not record or not usage_complete:
        return _REVIEW, ["usage_evidence_incomplete"]

    created = _created_timestamp(record, path)
    if created is None:
        return _REVIEW, ["usage_evidence_incomplete"]
    idle_days = max(0, int((now - created) // _ONE_DAY_SECONDS))
    if record.get("created_by") == "agent" and idle_days >= archive_days:
        return _STALE, ["idle_after_threshold"]
    if idle_days < min(window_days, archive_days):
        return _REVIEW, ["too_new"]
    return _REVIEW, ["insufficient_activity_evidence"]


def _catalog_rows(
    *,
    catalog: Sequence[Mapping[str, Any]],
    raw_paths: Sequence[Path],
    unreadable_paths: set[str],
    usage: Mapping[str, Mapping[str, Any]],
    now: float,
    window_days: int,
    archive_days: int,
    cron_names: set[str],
    hub_names: set[str],
    external_names: set[str],
    modified_names: set[str],
) -> tuple[list[dict[str, Any]], bool]:
    raw_counts = Counter(_path_key(path) for path in raw_paths)
    catalog_counts = Counter(_path_key(item.get("path")) for item in catalog)
    path_counts = Counter(
        {
            key: max(raw_counts[key], catalog_counts[key])
            for key in raw_counts.keys() | catalog_counts.keys()
        }
    )
    rows: list[dict[str, Any]] = []
    evidence_complete = True

    for item in catalog:
        path = Path(str(item.get("path") or ""))
        name = str(item.get("load_name") or item.get("name") or path.parent.name or "unknown")
        key = _path_key(path)
        record = usage.get(name)
        usage_complete = isinstance(record, Mapping) and _created_timestamp(record, path) is not None
        evidence_complete = evidence_complete and usage_complete
        broken: list[str] = []
        if key in unreadable_paths or not path.is_file():
            broken.append("unreadable_skill")
        if path_counts[key] > 1 or (item.get("status") == "ambiguous" and not item.get("load_name")):
            broken.append("duplicate_discovery_path")
        status, reasons = _recommendation(
            name,
            path=path,
            broken_reasons=broken,
            record=record,
            usage_complete=usage_complete,
            now=now,
            window_days=window_days,
            archive_days=archive_days,
            cron_names=cron_names,
            hub_names=hub_names,
            external_names=external_names,
            modified_names=modified_names,
        )
        rows.append(
            {
                "skill": name,
                "path": path,
                "status": status,
                "reasons": reasons,
                "record": record,
            }
        )

    parsed_paths = {_path_key(row["path"]) for row in rows}
    for key in sorted(unreadable_paths - parsed_paths):
        name = Path(key).parent.name if key else "unknown"
        rows.append(
            {
                "skill": name,
                "path": Path(key) if key else Path(),
                "status": _BROKEN,
                "reasons": ["unreadable_skill"],
                "record": usage.get(name),
            }
        )
        evidence_complete = False
    return rows, evidence_complete


def _metadata_chars(catalog: Sequence[Mapping[str, Any]]) -> int:
    """Characters the rendered skills index spends on each visible metadata row."""
    from agent.skill_utils import TIER_PROJECT, extract_skill_description

    categories: set[str] = set()
    entries: set[tuple[str, str]] = set()
    total = 0
    for item in catalog:
        name = str(item.get("load_name") or item.get("name") or "").strip()
        if not name:
            continue
        relative = Path(str(item.get("relative_path") or ""))
        category = "/".join(relative.parts[:-1]) or "general"
        key = (category, name)
        if key in entries:
            continue
        entries.add(key)
        categories.add(category)
        description = extract_skill_description(
            {"description": item.get("description") or ""}
        )
        if item.get("tier") == TIER_PROJECT:
            description = f"[project] {description}".strip()
        total += len("    - ") + len(name)
        if description:
            total += len(": ") + len(description)
    total += sum(len("  ") + len(category) + len(":") for category in categories)
    return total


def _growth_windows(
    rows: Sequence[Mapping[str, Any]],
    ledger_entries: Sequence[Mapping[str, Any]],
    *,
    now: float,
) -> dict[str, int]:
    created: dict[str, float] = {}
    for entry in ledger_entries:
        if entry.get("action") != "create" or not entry.get("skill"):
            continue
        timestamp = _timestamp(entry.get("ts"))
        if timestamp is not None:
            created[str(entry["skill"])] = max(timestamp, created.get(str(entry["skill"]), 0))
    for row in rows:
        name = str(row["skill"])
        if name in created:
            continue
        timestamp = _created_timestamp(row.get("record"), Path(str(row["path"])))
        if timestamp is not None:
            created[name] = timestamp
    return {
        "last_7_days": sum(1 for value in created.values() if now - value <= 7 * _ONE_DAY_SECONDS),
        "last_30_days": sum(1 for value in created.values() if now - value <= 30 * _ONE_DAY_SECONDS),
    }


def _target_names(record: Mapping[str, Any]) -> set[str]:
    target = record.get("target") if isinstance(record.get("target"), Mapping) else {}
    operation = record.get("operation") if isinstance(record.get("operation"), Mapping) else {}
    names = {
        str(value)
        for value in (
            target.get("name"),
            *(
                target.get("names", [])
                if isinstance(target.get("names"), list)
                else [target.get("names")]
            ),
        )
        if value
    }
    operations = (
        operation.get("operations", [])
        if operation.get("action") == "batch"
        else [operation]
    )
    names.update(
        str(item.get("name"))
        for item in operations
        if isinstance(item, Mapping) and item.get("name")
    )
    return names


def _anchor_keys(record: Mapping[str, Any]) -> set[str]:
    operation = record.get("operation") if isinstance(record.get("operation"), Mapping) else {}
    operations = (
        operation.get("operations", [])
        if operation.get("action") == "batch"
        else [operation]
    )
    return {
        str(item.get("anchor_key"))
        for item in operations
        if isinstance(item, Mapping)
        and item.get("action") == "patch"
        and item.get("anchor_key")
    }


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _proposal_metrics(
    records: Sequence[Mapping[str, Any]],
    queue: Mapping[str, Any],
    *,
    library_names: set[str],
    stale_names: set[str],
) -> dict[str, Any]:
    statuses = Counter(str(record.get("status") or "pending") for record in records)
    pending = [
        record
        for record in records
        if record.get("status") in {"pending", "claiming"}
    ]
    terminal = statuses["applied"] + statuses["rejected"] + statuses["expired"]
    targets: Counter[str] = Counter()
    anchors: Counter[str] = Counter()
    for record in pending:
        targets.update(_target_names(record))
        anchors.update(_anchor_keys(record))
    handling = [
        float(record["updated_at"]) - float(record["created_at"])
        for record in records
        if record.get("status") in {"applied", "rejected", "expired"}
        and isinstance(record.get("updated_at"), (int, float))
        and isinstance(record.get("created_at"), (int, float))
        and float(record["updated_at"]) >= float(record["created_at"])
    ]
    duplicates = {
        str(item.get("id"))
        for record in pending
        if isinstance(record.get("related"), Mapping)
        for item in record["related"].get("possible_duplicates", [])
        if isinstance(item, Mapping) and item.get("id")
    }
    delayed_targets = {
        name for name in targets if name not in library_names or name in stale_names
    } | {
        name
        for record in pending
        if record.get("conflict") == "target_changed"
        for name in _target_names(record)
    }
    delayed_anchors = {
        key
        for record in pending
        if record.get("conflict") == "anchor_stale"
        for key in _anchor_keys(record)
    } | {
        key
        for record in pending
        if _target_names(record) & delayed_targets
        for key in _anchor_keys(record)
    }
    return {
        "pending": len(pending),
        "applied": statuses["applied"],
        "rejected": statuses["rejected"],
        "expired": statuses["expired"],
        "broken": max(0, int(queue.get("broken_count") or 0)),
        "approval_rate": _rate(statuses["applied"], terminal),
        "rejection_rate": _rate(statuses["rejected"], terminal),
        "expiration_rate": _rate(statuses["expired"], terminal),
        "median_handling_seconds": (
            round(float(statistics.median(handling)), 3) if handling else None
        ),
        "max_pending_per_target": max(targets.values(), default=0),
        "max_pending_per_anchor": max(anchors.values(), default=0),
        "stale_targets": len(delayed_targets),
        "stale_anchors": len(delayed_anchors),
        "possible_duplicates": len(duplicates),
    }


def build_skill_health_report(*, days: int = 30, now: float | None = None) -> dict[str, Any]:
    """Build a deterministic, profile-scoped, read-only skill health snapshot."""
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 365:
        raise ValueError("days must be an integer between 1 and 365")

    timestamp = float(now if now is not None else datetime.now(UTC).timestamp())
    archive_days = max(1, curator_archive_after_days())
    usage = load_usage()
    catalog, raw_paths, unreadable = _skill_catalog_snapshot()
    cron_names = _cron_referenced_skill_names()
    hub_names = _hub_installed_skill_names()
    external_names = _external_skill_names()
    modified_names = _modified_skill_names()
    archived_names = _archived_skill_names()
    ledger_entries = _ledger_entries()
    learning_config = _skill_learning_config()

    rows, usage_complete = _catalog_rows(
        catalog=catalog,
        raw_paths=raw_paths,
        unreadable_paths=unreadable,
        usage=usage,
        now=timestamp,
        window_days=days,
        archive_days=archive_days,
        cron_names=cron_names,
        hub_names=hub_names,
        external_names=external_names,
        modified_names=modified_names,
    )
    rows.sort(
        key=lambda row: (
            {_BROKEN: 0, _STALE: 1, _REVIEW: 2, _KEEP: 3}[row["status"]],
            row["skill"],
            str(row["path"]),
        )
    )

    metadata_chars = _metadata_chars(catalog)

    status_counts = Counter(row["status"] for row in rows)
    proposals = _proposal_metrics(
        _proposal_records(learning_config),
        _proposal_queue(timestamp, learning_config),
        library_names={str(row["skill"]) for row in rows},
        stale_names={str(row["skill"]) for row in rows if row["status"] == _STALE},
    )
    broken = status_counts[_BROKEN]
    evidence_complete = (
        usage_complete
        and not unreadable
        and not any("duplicate_discovery_path" in row["reasons"] for row in rows)
    )

    return {
        "schema_version": 1,
        "generated_at": datetime.fromtimestamp(timestamp, UTC).isoformat(),
        "window_days": days,
        "evidence_complete": evidence_complete,
        "library": {
            "total": len(rows),
            "active": status_counts[_KEEP] + status_counts[_REVIEW],
            "stale": status_counts[_STALE],
            "archived": len(archived_names),
            "broken": broken,
            "metadata_chars": metadata_chars,
            "estimated_tokens": math.ceil(metadata_chars / 4) if metadata_chars else 0,
            "growth": _growth_windows(rows, ledger_entries, now=timestamp),
        },
        "proposals": proposals,
        "recommendations": [
            {
                "skill": row["skill"],
                "status": row["status"],
                "reasons": row["reasons"],
            }
            for row in rows
        ],
    }


def render_skill_health_text(report: Mapping[str, Any]) -> str:
    """Format a report without reading or mutating any application state."""
    library = report.get("library") if isinstance(report.get("library"), Mapping) else {}
    proposals = report.get("proposals") if isinstance(report.get("proposals"), Mapping) else {}
    growth = library.get("growth") if isinstance(library.get("growth"), Mapping) else {}
    recommendations = report.get("recommendations") or []
    evidence = "complete" if report.get("evidence_complete") else "incomplete"
    lines = [
        f"Library health (last {report.get('window_days', 0)} days)",
        f"  Evidence: {evidence}",
        f"  Skills: total={library.get('total', 0)} active={library.get('active', 0)} "
        f"stale={library.get('stale', 0)} archived={library.get('archived', 0)} "
        f"broken={library.get('broken', 0)}",
        f"  Metadata: {library.get('metadata_chars', 0)} chars "
        f"(~{library.get('estimated_tokens', 0)} tokens)",
        f"  Growth: 7d={growth.get('last_7_days', 0)} 30d={growth.get('last_30_days', 0)}",
        f"  Proposals: pending={proposals.get('pending', 0)} applied={proposals.get('applied', 0)} "
        f"rejected={proposals.get('rejected', 0)} expired={proposals.get('expired', 0)} "
        f"broken={proposals.get('broken', 0)}",
        "Recommendations:",
    ]
    if not recommendations:
        lines.append("  (none)")
    for row in recommendations:
        reasons = ",".join(str(reason) for reason in row.get("reasons", []))
        lines.append(f"  {row.get('status', 'REVIEW')} {row.get('skill', '?')} [{reasons}]")
    return "\n".join(lines)


__all__ = [
    "RECOMMENDATION_STATUSES",
    "build_skill_health_report",
    "curator_archive_after_days",
    "load_usage",
    "render_skill_health_text",
]
