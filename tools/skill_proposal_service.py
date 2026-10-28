"""Build, validate, and transition immutable skill proposal snapshots."""

from __future__ import annotations

import hashlib
import json
import secrets
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
        "claimed": "proposal_in_review",
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
    current = get_skill_proposal(proposal_id, now=now)
    if current is None:
        return {"success": False, "error": "not_found"}

    owner = f"approval-{secrets.token_hex(8)}"
    claimed = claim_skill_proposal(
        proposal_id,
        owner=owner,
        expected_revision=revision,
        expected_review_hash=review_hash,
        now=now,
    )
    if claimed is None:
        return {"success": False, "error": "already_being_reviewed"}
    if claimed.get("status") == "expired":
        return {"success": False, "error": "expired"}
    if claimed.get("status") == "review_hash_mismatch":
        latest = claimed.get("proposal") if isinstance(claimed.get("proposal"), Mapping) else {}
        return {
            "success": False,
            "error": "review_hash_mismatch",
            "current_revision": latest.get("revision"),
            "current_review_hash": latest.get("review_hash"),
        }
    if conflict := claimed.get("conflict"):
        release_skill_proposal(proposal_id, owner=owner)
        return {"success": False, "error": str(conflict), "proposal": claimed}
    try:
        fresh_base = base_hash_digest(operation_base_hashes(claimed["operation"]))
        if fresh_base != base_hash or fresh_base != claimed.get("base_hash"):
            return _release_review_change(
                proposal_id,
                owner=owner,
                proposal=claimed,
                error="target_changed",
            )
        validation = validate_proposed_operation(claimed["operation"])
        if validation is not None:
            if validation in {"target_changed", "anchor_stale"}:
                return _release_review_change(
                    proposal_id,
                    owner=owner,
                    proposal=claimed,
                    error=validation,
                )
            if validation in {"blocked_by_lint", "blocked_by_security"}:
                return _release_review_change(
                    proposal_id,
                    owner=owner,
                    proposal=claimed,
                    error="review_refresh_required",
                    last_error=validation,
                )
            release_skill_proposal(proposal_id, owner=owner)
            return {"success": False, "error": validation, "proposal": claimed}
        applied = apply_fn(claimed)
        if isinstance(applied, str):
            applied = json.loads(applied)
        if not applied.get("success"):
            mapped = applied.get("error")
            if mapped in {"target_changed", "anchor_stale"}:
                return _release_review_change(
                    proposal_id,
                    owner=owner,
                    proposal=claimed,
                    error=str(mapped),
                )
            if mapped in {"blocked_by_lint", "blocked_by_security"}:
                return _release_review_change(
                    proposal_id,
                    owner=owner,
                    proposal=claimed,
                    error="review_refresh_required",
                    last_error=str(mapped),
                )
            mapped = "apply_failed"
            released = release_skill_proposal(
                proposal_id,
                owner=owner,
                last_error=str(applied.get("error", "apply failed")),
            )
            return {"success": False, "error": mapped, "proposal": released}
        finished = finish_skill_proposal(
            proposal_id,
            status="applied",
            review_hash=review_hash,
            owner=owner,
            now=now,
        )
        if finished.get("status") == "applied":
            return {"success": True, "proposal": finished}
        release_skill_proposal(proposal_id, owner=owner)
        return {"success": False, "error": "already_being_reviewed", "proposal": finished}
    finally:
        release_skill_proposal(proposal_id, owner=owner)


def reject_skill_proposal(
    proposal_id: str, *, review_hash: str, now: float | None = None
) -> dict[str, Any]:
    current = get_skill_proposal(proposal_id, now=now)
    if current is None:
        return {"success": False, "error": "not_found"}
    owner = f"reject-{secrets.token_hex(8)}"
    claimed = claim_skill_proposal(
        proposal_id,
        owner=owner,
        expected_review_hash=review_hash,
        now=now,
    )
    if claimed is None:
        return {"success": False, "error": "already_being_reviewed"}
    if claimed.get("status") == "expired":
        return {"success": False, "error": "expired"}
    if claimed.get("status") == "review_hash_mismatch":
        return {"success": False, "error": "review_hash_mismatch"}
    try:
        finished = finish_skill_proposal(
            proposal_id,
            status="rejected",
            review_hash=review_hash,
            owner=owner,
            now=now,
        )
        if finished.get("status") == "rejected":
            return {"success": True, "proposal": finished}
        return {"success": False, "error": "already_being_reviewed", "proposal": finished}
    finally:
        release_skill_proposal(proposal_id, owner=owner)


def _release_review_change(
    proposal_id: str,
    *,
    owner: str,
    proposal: Mapping[str, Any],
    error: str,
    last_error: str | None = None,
) -> dict[str, Any]:
    revision = int(proposal.get("revision", 1)) + 1
    snapshot = {**proposal, "revision": revision, "conflict": error}
    review_hash = compute_review_hash(snapshot)
    released = release_skill_proposal(
        proposal_id,
        owner=owner,
        conflict=error,
        revision=revision,
        review_hash=review_hash,
        last_error=last_error,
    )
    return {
        "success": False,
        "error": error,
        "proposal": released,
        "current_revision": released.get("revision"),
        "current_review_hash": released.get("review_hash"),
    }


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
