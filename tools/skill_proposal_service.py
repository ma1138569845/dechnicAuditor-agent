"""Build, validate, and transition immutable skill proposal snapshots."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from typing import Any

from tools.skill_intent import SkillWriteIntentContext
from tools.skill_evidence import validate_proposal_evidence
from tools.skill_proposal_candidate import (
    base_hash_digest,
    canonicalize_operation,
    operation_base_hashes,
    operation_target_names,
    validate_proposed_operation,
)
from tools.skill_proposals import (
    claim_skill_proposal,
    create_skill_proposal,
    finish_skill_proposal,
    get_skill_proposal,
    proposal_fingerprint,
    release_skill_proposal,
    update_skill_proposal_review,
)

__all__ = [
    "approve_skill_proposal",
    "build_proposal_snapshot",
    "compute_base_hash",
    "compute_review_hash",
    "reject_skill_proposal",
    "submit_skill_proposal",
]


def compute_base_hash(skill_dir):
    from tools.skill_proposal_candidate import compute_base_hash as _compute_base_hash

    return _compute_base_hash(skill_dir)


def build_proposal_snapshot(
    operation: dict[str, Any],
    evidence: list[dict[str, Any]],
    context: SkillWriteIntentContext,
    *,
    now: float | None = None,
) -> dict[str, Any]:
    canonical_operation = canonicalize_operation(operation)
    target_names = operation_target_names(canonical_operation)
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
        "base_hash": canonical_operation["base_hash"],
        "target_names": target_names,
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


def submit_skill_proposal(
    operation: dict[str, Any],
    evidence: list[dict[str, Any]],
    context: SkillWriteIntentContext,
    *,
    now: float | None = None,
) -> dict[str, Any]:
    evidence_result = validate_proposal_evidence(evidence, context)
    if not evidence_result.ok:
        return {"success": False, "error": evidence_result.error}
    evidence = list(evidence_result.normalized)
    snapshot = build_proposal_snapshot(operation, evidence, context, now=now)
    validation = validate_proposed_operation(snapshot["operation"])
    if validation is not None:
        return {"success": False, "error": validation}
    snapshot["lint"] = []
    snapshot["security"] = {"verdict": "safe", "findings": []}
    fingerprint = proposal_fingerprint(snapshot["operation"])
    record = {
        "schema_version": 2,
        "status": "pending",
        "revision": 1,
        "target": {
            "name": snapshot["target_names"][0],
            "names": snapshot["target_names"],
        },
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
    if result.status == "merged" and result.proposal is not None:
        result.proposal["review_hash"] = compute_review_hash(result.proposal)
        update_skill_proposal_review(
            str(result.proposal["id"]),
            review_hash=str(result.proposal["review_hash"]),
        )
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
        fresh_base = base_hash_digest(operation_base_hashes(current["operation"]))
        if fresh_base != base_hash or fresh_base != current.get("base_hash"):
            released = release_skill_proposal(proposal_id, owner="approval", conflict="target_changed")
            released["revision"] = int(released.get("revision", 1)) + 1
            return {"success": False, "error": "target_changed", "proposal": released}
        validation = validate_proposed_operation(current["operation"])
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
            if mapped not in {
                "target_changed",
                "anchor_stale",
                "unsafe_target",
                "blocked_by_lint",
                "blocked_by_security",
            }:
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


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
