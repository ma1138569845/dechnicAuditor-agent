"""Build, validate, and transition immutable skill proposal snapshots."""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home
from tools.skill_intent import SkillWriteIntentContext
from tools.skill_linter import lint_content
from tools.skill_proposals import (
    claim_skill_proposal,
    create_skill_proposal,
    finish_skill_proposal,
    get_skill_proposal,
    proposal_fingerprint,
    release_skill_proposal,
)
from tools.skills_guard import scan_skill, should_allow_install


def build_proposal_snapshot(
    operation: dict[str, Any],
    evidence: list[dict[str, Any]],
    context: SkillWriteIntentContext,
    *,
    now: float | None = None,
) -> dict[str, Any]:
    canonical_operation = _canonical_operation(operation)
    return {
        "schema_version": 2,
        "operation": canonical_operation,
        "evidence": evidence,
        "context": {
            "intent": context.intent.value,
            "origin": context.origin,
            "attended": context.attended,
            "task_id": context.task_id,
            "session_id": context.session_id,
            "review_run_id": context.review_run_id,
            "review_message_refs": sorted(context.review_message_refs),
            "review_snapshot_digest": context.review_snapshot_digest,
        },
        "base_hash": compute_base_hash(_target_dir(canonical_operation["name"])),
        "validated_at": now,
    }


def compute_review_hash(snapshot: Mapping[str, Any]) -> str:
    payload = {
        "schema_version": snapshot.get("schema_version"),
        "revision": snapshot.get("revision", 1),
        "operation_digest": proposal_fingerprint(snapshot["operation"]),
        "evidence_digest": _digest(snapshot.get("evidence", [])),
        "evidence_count": len(snapshot.get("evidence", [])),
        "diff_digest": _digest(snapshot["operation"]),
        "base_hash": snapshot.get("base_hash"),
        "lint": snapshot.get("lint", []),
        "security": snapshot.get("security", {}),
        "conflict": snapshot.get("conflict"),
        "related_decision_state": snapshot.get("related", {}),
    }
    return _digest(payload)


def compute_base_hash(skill_dir: Path | None) -> str:
    entries: list[tuple[str, str]] = []
    if skill_dir is not None and skill_dir.exists():
        for path in sorted(item for item in skill_dir.rglob("*") if item.is_file()):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            entries.append((path.relative_to(skill_dir).as_posix(), f"sha256:{digest}"))
    return _digest(entries)


def submit_skill_proposal(
    operation: dict[str, Any],
    evidence: list[dict[str, Any]],
    context: SkillWriteIntentContext,
    *,
    now: float | None = None,
) -> dict[str, Any]:
    snapshot = build_proposal_snapshot(operation, evidence, context, now=now)
    validation = _validate_candidate(snapshot["operation"])
    if validation is not None:
        return {"success": False, "error": validation}
    snapshot["lint"] = []
    snapshot["security"] = {"verdict": "safe", "findings": []}
    fingerprint = proposal_fingerprint(snapshot["operation"])
    record = {
        "schema_version": 2,
        "status": "pending",
        "revision": 1,
        "target": {"name": snapshot["operation"]["name"]},
        "operation": snapshot["operation"],
        "evidence": evidence,
        "provenance": {
            "origin": context.origin,
            "review_run_id": context.review_run_id,
            "task_id": context.task_id,
            "session_id": context.session_id,
        },
        "fingerprint": fingerprint,
        "base_hash": snapshot["base_hash"],
        "review_hash": compute_review_hash(snapshot),
        "review_snapshot_digest": context.review_snapshot_digest or _digest(snapshot),
    }
    result = create_skill_proposal(record, now=now)
    mapping = {
        "profile_full": "proposal_inbox_full",
        "target_full": "proposal_target_full",
        "anchor_occupied": "anchor_occupied",
        "invalid_proposal": "invalid_proposal",
    }
    if result.status in mapping:
        return {"success": False, "error": mapping[result.status]}
    proposal = result.proposal or {}
    return {
        "success": True,
        "proposal_staged": True,
        "pending_id": proposal["id"],
        "revision": proposal["revision"],
        "review_hash": proposal["review_hash"],
        "base_hash": proposal["base_hash"],
    }


def approve_skill_proposal(
    proposal_id: str,
    *,
    revision: int,
    review_hash: str,
    base_hash: str,
    apply_fn: Callable[[dict[str, Any]], str | dict[str, Any]],
    now: float | None = None,
) -> dict[str, Any]:
    current = get_skill_proposal(proposal_id)
    if current is None:
        return {"success": False, "error": "not_found"}
    if current.get("revision") != revision or current.get("review_hash") != review_hash:
        return {
            "success": False,
            "error": "review_hash_mismatch",
            "current_review_hash": current.get("review_hash"),
        }
    claimed = claim_skill_proposal(proposal_id, owner="approval", now=now)
    if claimed is None:
        return {"success": False, "error": "already_being_reviewed"}
    try:
        fresh_base = compute_base_hash(_target_dir(current["target"]["name"]))
        if fresh_base != base_hash or fresh_base != current.get("base_hash"):
            released = release_skill_proposal(proposal_id, owner="approval", conflict="target_changed")
            released["revision"] = int(released.get("revision", 1)) + 1
            return {"success": False, "error": "target_changed", "proposal": released}
        validation = _validate_candidate(current["operation"])
        if validation is not None:
            released = release_skill_proposal(proposal_id, owner="approval")
            return {"success": False, "error": validation, "proposal": released}
        applied = apply_fn(current)
        if isinstance(applied, str):
            applied = json.loads(applied)
        if not applied.get("success"):
            released = release_skill_proposal(proposal_id, owner="approval")
            released["last_error"] = applied.get("error", "apply failed")
            mapped = applied.get("error")
            if mapped not in {"target_changed", "anchor_stale", "blocked_by_lint", "blocked_by_security"}:
                mapped = "apply_failed"
            return {"success": False, "error": mapped, "proposal": released}
        finished = finish_skill_proposal(
            proposal_id,
            status="applied",
            review_hash=review_hash,
            now=now,
        )
        return {"success": True, "proposal": finished}
    finally:
        release_skill_proposal(proposal_id, owner="approval")


def reject_skill_proposal(
    proposal_id: str, *, review_hash: str, now: float | None = None
) -> dict[str, Any]:
    current = get_skill_proposal(proposal_id)
    if current is None:
        return {"success": False, "error": "not_found"}
    if current.get("review_hash") != review_hash:
        return {"success": False, "error": "review_hash_mismatch"}
    finished = finish_skill_proposal(
        proposal_id,
        status="rejected",
        review_hash=review_hash,
        now=now,
    )
    return {"success": finished.get("status") == "rejected", "proposal": finished}


def _canonical_operation(operation: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(operation)
    result["file_path"] = str(result.get("file_path", "SKILL.md")).replace("\\", "/")
    for key in ("content", "old_string", "new_string"):
        if isinstance(result.get(key), str):
            result[key] = result[key].replace("\r\n", "\n")
    if result.get("action") == "patch":
        result["anchor_key"] = _digest({
            "skill": result.get("name"),
            "file_path": result["file_path"],
            "normalized_old_string": result.get("old_string", ""),
        })
        result["result_digest"] = _digest(result.get("new_string", ""))
    else:
        result["anchor_key"] = None
        result["result_digest"] = _digest(result.get("content", ""))
    result["base_hash"] = compute_base_hash(_target_dir(str(result.get("name", ""))))
    return result


def _validate_candidate(operation: Mapping[str, Any]) -> str | None:
    content = operation.get("content")
    if operation.get("action") == "patch":
        target = _target_dir(str(operation.get("name", "")))
        source = target / str(operation.get("file_path", "SKILL.md"))
        if not source.exists() or operation.get("old_string", "") not in source.read_text(encoding="utf-8"):
            return "unsafe_target"
        content = source.read_text(encoding="utf-8").replace(
            operation.get("old_string", ""), operation.get("new_string", ""), 1
        )
    if not isinstance(content, str):
        return "not_staged"
    if any(item.severity == "error" for item in lint_content(content)):
        return "blocked_by_lint"
    temp_root = get_hermes_home() / ".skill-proposal-tmp" / uuid.uuid4().hex / str(operation.get("name", "skill"))
    try:
        temp_root.mkdir(parents=True)
        (temp_root / "SKILL.md").write_text(content, encoding="utf-8")
        allowed, _reason = should_allow_install(scan_skill(temp_root, source="agent"), force=False)
        if allowed is not True:
            return "blocked_by_security"
    finally:
        shutil.rmtree(temp_root.parent, ignore_errors=True)
    return None


def _target_dir(name: str) -> Path | None:
    path = get_hermes_home() / "skills" / name
    return path if path.exists() else None


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
