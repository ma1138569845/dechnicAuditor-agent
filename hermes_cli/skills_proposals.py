"""Human-facing CLI and slash presentation for skill proposals."""

from __future__ import annotations

import sys
import time
from collections.abc import Mapping, Sequence
from typing import Any

from tools import write_approval as wa
from tools.skill_proposal_service import approve_skill_proposal, reject_skill_proposal
from tools.skill_proposals import (
    get_skill_proposal,
    get_skill_proposal_queue_state,
    list_skill_proposals,
)


def has_pending_skill_reviews() -> bool:
    return get_skill_proposal_queue_state()["pending_count"] > 0


def skill_review_surface_available(write_approval_enabled: bool) -> bool:
    """The approval toggle controls new legacy staging, not reviewability of existing records."""
    return (
        write_approval_enabled
        or wa.pending_count(wa.SKILLS) > 0
        or has_pending_skill_reviews()
    )


def _target_name(record: Mapping[str, Any]) -> str:
    target = record.get("target") if isinstance(record.get("target"), Mapping) else {}
    operation = record.get("operation") if isinstance(record.get("operation"), Mapping) else {}
    return str(
        target.get("name")
        or target.get("skill")
        or operation.get("name")
        or "unknown"
    )


def _action(record: Mapping[str, Any]) -> str:
    operation = record.get("operation") if isinstance(record.get("operation"), Mapping) else {}
    return str(operation.get("action") or record.get("action") or "unknown")


def _evidence(record: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    evidence = record.get("evidence")
    return [item for item in evidence or [] if isinstance(item, Mapping)]


def _evidence_count(record: Mapping[str, Any]) -> int:
    count = record.get("evidence_count")
    return count if isinstance(count, int) and count >= 0 else len(_evidence(record))


def _evidence_kinds(record: Mapping[str, Any]) -> str:
    kinds = list(dict.fromkeys(str(item.get("kind")) for item in _evidence(record) if item.get("kind")))
    return ",".join(kinds) if kinds else "none"


def _status(record: Mapping[str, Any]) -> str:
    return str(record.get("conflict") or record.get("status") or "pending")


def _expires(record: Mapping[str, Any], now: float) -> str:
    expires_at = record.get("expires_at")
    if not isinstance(expires_at, (int, float)):
        return "unknown"
    days = max(0, int((float(expires_at) - now) // 86400))
    return f"{days}d"


def format_skill_proposal_list(
    records: Sequence[Mapping[str, Any]], *, now: float | None = None
) -> str:
    timestamp = time.time() if now is None else now
    if not records:
        return "No pending skill proposals."
    lines = [f"Pending skill proposals ({len(records)}):"]
    for record in records:
        legacy = record.get("schema_version") != 2
        label = "[legacy] " if legacy else ""
        lines.append(
            f"  {label}{record.get('id', '?')}  {_target_name(record)}  {_action(record)}  "
            f"{_status(record)}  evidence={_evidence_count(record)}  "
            f"kinds={_evidence_kinds(record)}  expires_in={_expires(record, timestamp)}"
        )
    lines.append("")
    lines.append("Show: /skills show <id>   Diff: /skills diff <id>")
    lines.append("Approve only from the revision shown in the detail view; reject remains available.")
    return "\n".join(lines)


def _preview_diff(record: Mapping[str, Any]) -> str:
    preview = record.get("preview")
    if isinstance(preview, Mapping) and isinstance(preview.get("diff"), str):
        return preview["diff"]
    operation = record.get("operation") if isinstance(record.get("operation"), Mapping) else {}
    if operation.get("action") == "patch":
        return (
            f"- {operation.get('old_string', '')}\n"
            f"+ {operation.get('new_string', '')}"
        )
    if isinstance(operation.get("content"), str):
        return operation["content"]
    if isinstance(operation.get("file_content"), str):
        return operation["file_content"]
    return f"{_action(record)} {_target_name(record)}"


def format_skill_proposal_detail(proposal: Mapping[str, Any]) -> str:
    if proposal.get("schema_version") != 2:
        return (
            f"# Legacy pending skill write {proposal.get('id', '?')}\n"
            f"target: {_target_name(proposal)}\n"
            f"action: {_action(proposal)}\n"
            "Legacy approval is disabled. Reject it and recreate the edit through an explicit "
            "user-authorized write.\n"
            f"/skills reject {proposal.get('id', '')}"
        )
    proposal_id = str(proposal.get("id") or "")
    revision = proposal.get("revision")
    lines = [
        f"# Skill proposal {proposal_id}",
        f"status: {_status(proposal)}",
        f"target: {_target_name(proposal)}",
        f"action: {_action(proposal)}",
        f"revision: {revision}",
        f"base_hash: {proposal.get('base_hash', '')}",
        f"review_hash: {proposal.get('review_hash', '')}",
        f"fingerprint: {proposal.get('fingerprint', '')}",
        "",
        "Evidence:",
    ]
    evidence = _evidence(proposal)
    if evidence:
        for item in evidence:
            refs = item.get("message_refs") if isinstance(item.get("message_refs"), list) else []
            lines.append(f"  - {item.get('kind', 'unknown')} refs={len(refs)}")
    else:
        lines.append("  - none")
    lines += ["", "Diff preview:", _preview_diff(proposal), ""]
    if proposal.get("conflict"):
        lines.append(f"conflict: {proposal['conflict']}")
    if proposal.get("failure"):
        lines.append(f"failure: {proposal['failure']}")
    lines += [
        f"Approve: /skills approve {proposal_id} {revision}",
        f"Reject:  /skills reject {proposal_id} {revision}",
        f"CLI:     hermes skills proposals approve {proposal_id} --revision {revision}",
        "",
        "Approval revalidates target, lint, and security against the exact reviewed snapshot.",
    ]
    return "\n".join(lines)


def execute_skill_proposal_command(
    action: str,
    target: str | None,
    *,
    reviewed_revision: int | None = None,
    profile: str | None = None,
) -> tuple[int, str, str]:
    del profile  # The CLI/profile and gateway scope already select HERMES_HOME.
    normalized = {
        "pending": "list",
        "show": "show",
        "diff": "show",
        "apply": "approve",
        "deny": "reject",
        "drop": "reject",
    }.get(action, action)
    if normalized == "list":
        return 0, format_skill_proposal_list(list_skill_proposals()), ""
    if not target:
        return 2, "", f"proposal id is required for {normalized}"
    if target.lower() == "all" and normalized == "approve":
        if any(item.get("schema_version") == 2 for item in list_skill_proposals()):
            return 2, "", "reviewed_revision_required"
    record = get_skill_proposal(target)
    if record is None:
        return 2, "", f"proposal_not_found: {target}"
    schema_version = record.get("schema_version")
    if normalized == "show":
        return 0, format_skill_proposal_detail(record), ""
    if schema_version != 2:
        if normalized == "approve":
            return 2, "", "legacy_pending_requires_explicit_edit"
        if normalized == "reject":
            removed = wa.discard_pending(wa.SKILLS, target)
            return (
                (0, f"Rejected legacy pending skill write '{target}'.", "")
                if removed
                else (2, "", f"proposal_not_found: {target}")
            )
        return 2, "", f"unsupported proposal action: {normalized}"
    revision = record.get("revision")
    if (
        not isinstance(reviewed_revision, int)
        or isinstance(reviewed_revision, bool)
        or reviewed_revision <= 0
    ):
        return 2, "", "reviewed_revision_required"
    if reviewed_revision != revision:
        return 2, "", "review_hash_mismatch"
    if normalized == "approve":
        from tools.skill_manager_tool import apply_skill_proposal

        result = approve_skill_proposal(
            target,
            revision=int(revision),
            review_hash=str(record.get("review_hash") or ""),
            base_hash=str(record.get("base_hash") or ""),
            apply_fn=apply_skill_proposal,
        )
        if result.get("success"):
            return 0, f"Approved skill proposal '{target}'.", ""
        return 2, "", str(result.get("error") or "approval_failed")
    if normalized == "reject":
        result = reject_skill_proposal(
            target, review_hash=str(record.get("review_hash") or "")
        )
        if result.get("success"):
            return 0, f"Rejected skill proposal '{target}'.", ""
        return 2, "", str(result.get("error") or "rejection_failed")
    return 2, "", f"unsupported proposal action: {normalized}"


def run_skill_proposal_command(
    action: str,
    target: str | None,
    *,
    reviewed_revision: int | None = None,
    profile: str | None = None,
) -> int:
    code, stdout, stderr = execute_skill_proposal_command(
        action,
        target,
        reviewed_revision=reviewed_revision,
        profile=profile,
    )
    if stdout:
        print(stdout)
    if stderr:
        print(stderr, file=sys.stderr)
    return code


__all__ = [
    "execute_skill_proposal_command",
    "format_skill_proposal_detail",
    "format_skill_proposal_list",
    "has_pending_skill_reviews",
    "run_skill_proposal_command",
    "skill_review_surface_available",
]
