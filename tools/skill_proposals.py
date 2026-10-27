"""Versioned, locked storage for skill proposals."""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping

from hermes_constants import get_hermes_home
from tools.skill_learning_config import SkillLearningConfig, get_skill_learning_config
from tools.skill_usage import skill_file_lock
from utils import atomic_json_write


_HASH_RE = r"^[0-9a-f]{64}$"
_HASH_FIELDS = ("fingerprint", "base_hash", "review_hash", "review_snapshot_digest")


@dataclass(frozen=True)
class ProposalCreateResult:
    status: str
    proposal: dict[str, Any] | None = None
    conflict: str | None = None


def proposal_fingerprint(operation: Mapping[str, Any]) -> str:
    canonical = json.dumps(operation, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def create_skill_proposal(
    record: Mapping[str, Any], *, now: float | None = None
) -> ProposalCreateResult:
    timestamp = time.time() if now is None else now
    with _store_lock():
        config = get_skill_learning_config()
        candidate = dict(record)
        if not _valid_v2(candidate):
            return ProposalCreateResult("invalid_proposal")
        active, _broken = _scan(config, timestamp)
        existing = next(
            (item for item in active if item["fingerprint"] == candidate["fingerprint"]),
            None,
        )
        if existing is not None:
            existing["evidence"] = [*existing.get("evidence", []), *candidate.get("evidence", [])]
            existing["revision"] = int(existing.get("revision", 1)) + 1
            existing["updated_at"] = timestamp
            existing["last_seen_at"] = timestamp
            _write_active(existing)
            return ProposalCreateResult("merged", existing)

        counts = _capacity_counts(active)
        if counts["total"] >= config.max_pending:
            return ProposalCreateResult("profile_full")
        for target in _target_names(candidate):
            if counts["targets"].get(target, 0) >= config.max_pending_per_target:
                return ProposalCreateResult("target_full")
        anchor = _anchor(candidate)
        if anchor and counts["anchors"].get(anchor, 0) >= config.max_pending_per_anchor:
            return ProposalCreateResult("anchor_occupied")

        proposal = {
            **candidate,
            "schema_version": 2,
            "id": "skp_" + secrets.token_hex(8),
            "status": "pending",
            "revision": 1,
            "created_at": timestamp,
            "updated_at": timestamp,
            "last_seen_at": timestamp,
            "expires_at": timestamp + config.proposal_ttl_days * 86400,
        }
        _write_active(proposal)
        return ProposalCreateResult("created", proposal)


def list_skill_proposals(
    status: str = "pending", *, now: float | None = None
) -> list[dict[str, Any]]:
    return read_skill_proposal_records(status=status, update_conflicts=False, now=now)


def read_skill_proposal_records(
    *,
    status: str = "pending",
    update_conflicts: bool = False,
    now: float | None = None,
) -> list[dict[str, Any]]:
    del update_conflicts  # Read paths never mutate conflict metadata.
    timestamp = time.time() if now is None else now
    config = get_skill_learning_config()
    active, _broken = _scan(config, timestamp)
    history = _read_history()
    expired_v1 = [item for item in active if item["schema_version"] == 1 and item["status"] == "expired"]
    pending = [item for item in active if item["status"] in {"pending", "claiming"}]
    views = {
        "pending": pending,
        "claiming": [item for item in active if item["schema_version"] == 2 and item["status"] == "claiming"],
        "applied": [item for item in history if item.get("status") == "applied"],
        "rejected": [item for item in history if item.get("status") == "rejected"],
        "expired": [*expired_v1, *(item for item in history if item.get("status") == "expired")],
        "history": [*expired_v1, *history],
        "all": [*active, *history],
    }
    if status not in views:
        raise ValueError(f"unsupported proposal status: {status}")
    return [dict(item) for item in views[status]]


def get_skill_proposal_queue_state(*, now: float | None = None) -> dict[str, Any]:
    timestamp = time.time() if now is None else now
    config = get_skill_learning_config()
    active, broken = _scan(config, timestamp)
    pending = [item for item in active if item["status"] in {"pending", "claiming"}]
    counts = _capacity_counts(pending)
    expiries = [item.get("expires_at") for item in pending if isinstance(item.get("expires_at"), (int, float))]
    return {
        "pending_count": len(pending),
        "max_pending": config.max_pending,
        "over_limit": len(pending) > config.max_pending,
        "targets_over_limit": sum(1 for count in counts["targets"].values() if count > config.max_pending_per_target),
        "earliest_expires_at": min(expiries) if expiries else None,
        "broken_count": broken,
    }


def get_skill_proposal(proposal_id: str) -> dict[str, Any] | None:
    return next((item for item in read_skill_proposal_records(status="all") if item.get("id") == proposal_id), None)


def update_skill_proposal_review(
    proposal_id: str, *, review_hash: str
) -> dict[str, Any] | None:
    """Update only the derived review hash after a fingerprint merge."""
    with _store_lock():
        record = _read_active(proposal_id)
        if record is None:
            return None
        record["review_hash"] = review_hash
        _write_active(record)
        return dict(record)


def claim_skill_proposal(
    proposal_id: str, *, owner: str, lease_seconds: int = 120, now: float | None = None
) -> dict[str, Any] | None:
    timestamp = time.time() if now is None else now
    with _store_lock():
        record = _read_active(proposal_id)
        if record is None or record.get("schema_version") != 2:
            return None
        if float(record.get("expires_at", 0)) <= timestamp:
            record["status"] = "expired"
            _move_to_history(record)
            return {"status": "expired"}
        lease_until = float(record.get("lease_until", 0))
        claimed_by = record.get("claimed_by")
        if record.get("status") == "claiming" and claimed_by != owner and lease_until > timestamp:
            return None
        record.update(
            status="claiming",
            claimed_by=owner,
            lease_until=timestamp + lease_seconds,
            updated_at=timestamp,
        )
        _write_active(record)
        return record


def release_skill_proposal(
    proposal_id: str, *, owner: str, conflict: str | None = None
) -> dict[str, Any]:
    with _store_lock():
        record = _read_active(proposal_id)
        if record is None or record.get("claimed_by") not in {None, owner}:
            return {"status": "conflict"}
        record["status"] = "pending"
        record.pop("claimed_by", None)
        record.pop("lease_until", None)
        if conflict:
            record["conflict"] = conflict
        _write_active(record)
        return record


def finish_skill_proposal(
    proposal_id: str, *, status: str, review_hash: str, now: float | None = None
) -> dict[str, Any]:
    timestamp = time.time() if now is None else now
    with _store_lock():
        history = _history_path(proposal_id)
        if history.exists():
            existing = json.loads(history.read_text(encoding="utf-8"))
            if existing.get("status") == status:
                return existing
            return {"status": "conflict", "proposal": existing}
        record = _read_active(proposal_id)
        if record is None or status not in {"applied", "rejected", "expired"}:
            return {"status": "conflict"}
        if record.get("review_hash") != review_hash:
            return {"status": "conflict", "proposal": record}
        record.update(status=status, updated_at=timestamp)
        _move_to_history(record)
        return record


def prune_proposal_store(*, now: float | None = None) -> dict[str, int]:
    timestamp = time.time() if now is None else now
    config = get_skill_learning_config()
    moved = 0
    with _store_lock():
        for path in _active_files():
            record = _read_json(path)
            if not isinstance(record, dict) or record.get("schema_version") != 2:
                continue
            if float(record.get("expires_at", timestamp + 1)) <= timestamp:
                record["status"] = "expired"
                _move_to_history(record)
                moved += 1
        cutoff = timestamp - config.history_retention_days * 86400
        for path in _history_dir().glob("*.json"):
            record = _read_json(path)
            if isinstance(record, dict) and float(record.get("updated_at", timestamp)) < cutoff:
                path.unlink()
    return {"expired": moved}


def _valid_v2(record: Mapping[str, Any]) -> bool:
    if record.get("schema_version") != 2:
        return False
    for field in _HASH_FIELDS:
        value = record.get(field)
        if not isinstance(value, str) or not value.startswith("sha256:") or not _is_hex(value[7:]):
            return False
    anchor = record.get("operation", {}).get("anchor_key")
    return anchor is None or (isinstance(anchor, str) and anchor.startswith("sha256:") and _is_hex(anchor[7:]))


def _is_hex(value: str) -> bool:
    import re
    return bool(re.fullmatch(_HASH_RE, value))


def _scan(config: SkillLearningConfig, now: float) -> tuple[list[dict[str, Any]], int]:
    records: list[dict[str, Any]] = []
    broken = 0
    for path in _active_files():
        raw = _read_json(path)
        if not isinstance(raw, dict):
            broken += 1
            continue
        if raw.get("schema_version") == 2:
            if not _valid_v2(raw):
                broken += 1
                continue
            raw["status"] = "expired" if float(raw.get("expires_at", now + 1)) <= now else raw.get("status", "pending")
            records.append(raw)
            continue
        if raw.get("schema_version") not in {None, 1}:
            broken += 1
            continue
        created = float(raw.get("created_at", now))
        records.append({
            **raw,
            "schema_version": 1,
            "revision": 1,
            "status": "expired" if created + config.proposal_ttl_days * 86400 <= now else "pending",
            "expires_at": created + config.proposal_ttl_days * 86400,
            "target": {"name": raw.get("payload", {}).get("name", raw.get("id", ""))},
            "fingerprint": None,
            "base_hash": None,
            "review_hash": None,
        })
    return records, broken


def _capacity_counts(records: list[dict[str, Any]]) -> dict[str, Any]:
    targets: dict[str, int] = {}
    anchors: dict[tuple[str, str, str], int] = {}
    for record in records:
        for target in _target_names(record):
            targets[target] = targets.get(target, 0) + 1
        anchor = _anchor(record)
        if anchor:
            anchors[anchor] = anchors.get(anchor, 0) + 1
    return {"total": len(records), "targets": targets, "anchors": anchors}


def _target_name(record: Mapping[str, Any]) -> str:
    return str(record.get("target", {}).get("name") or record.get("operation", {}).get("name") or "")


def _target_names(record: Mapping[str, Any]) -> list[str]:
    target = record.get("target", {})
    names = target.get("names") if isinstance(target, Mapping) else None
    if isinstance(names, list) and names:
        return [str(name) for name in names if name]
    name = _target_name(record)
    return [name] if name else []


def _anchor(record: Mapping[str, Any]) -> tuple[str, str, str] | None:
    operation = record.get("operation", {})
    if operation.get("action") != "patch" or not operation.get("anchor_key"):
        return None
    return (_target_name(record), str(operation.get("file_path", "")), str(operation["anchor_key"]))


def _root() -> Path:
    return get_hermes_home() / "pending" / "skills"


def _history_dir() -> Path:
    return _root() / ".history"


def _active_files() -> list[Path]:
    root = _root()
    return sorted(path for path in root.glob("*.json") if path.is_file()) if root.exists() else []


def _read_history() -> list[dict[str, Any]]:
    directory = _history_dir()
    if not directory.exists():
        return []
    return [item for path in sorted(directory.glob("*.json")) if isinstance(item := _read_json(path), dict)]


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def _active_path(proposal_id: str) -> Path:
    return _root() / f"{proposal_id}.json"


def _history_path(proposal_id: str) -> Path:
    return _history_dir() / f"{proposal_id}.json"


def _read_active(proposal_id: str) -> dict[str, Any] | None:
    value = _read_json(_active_path(proposal_id))
    return value if isinstance(value, dict) else None


def _write_active(record: Mapping[str, Any]) -> None:
    path = _active_path(str(record["id"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_json_write(path, dict(record), mode=0o600)


def _move_to_history(record: dict[str, Any]) -> None:
    path = _history_path(str(record["id"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_json_write(path, record, mode=0o600)
    _active_path(str(record["id"])).unlink(missing_ok=True)


@contextmanager
def _store_lock() -> Iterator[None]:
    with skill_file_lock(_root() / ".locks" / "store.lock"):
        yield
