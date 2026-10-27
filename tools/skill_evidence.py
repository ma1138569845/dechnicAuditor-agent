"""Fail-closed validation for skill proposal evidence."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from tools.skill_intent import SkillWriteIntentContext


_KINDS = {"user_request", "user_correction", "skill_incomplete", "repeated_class"}
_SECRET_RE = re.compile(
    r"(?i)(password\s*=|api[_-]?key|secret|token|private key|aws_|sk-|ghp_|github_pat_)"
)


@dataclass(frozen=True)
class EvidenceResult:
    ok: bool
    error: str | None = None
    normalized: tuple[dict[str, Any], ...] = ()
    digest: str | None = None


def validate_proposal_evidence(
    evidence: Any, context: SkillWriteIntentContext
) -> EvidenceResult:
    if not isinstance(evidence, list) or not evidence:
        return EvidenceResult(False, "invalid_evidence")
    normalized: list[dict[str, Any]] = []
    for item in evidence:
        if not isinstance(item, Mapping) or item.get("kind") not in _KINDS:
            return EvidenceResult(False, "invalid_evidence")
        refs = item.get("message_refs")
        if not isinstance(refs, list) or not refs or any(not isinstance(ref, int) or ref <= 0 for ref in refs):
            return EvidenceResult(False, "invalid_evidence")
        unique_refs = tuple(dict.fromkeys(refs))
        if any(ref not in context.review_message_refs for ref in unique_refs):
            return EvidenceResult(False, "unverified_message_ref")
        if item["kind"] == "repeated_class" and len(unique_refs) < 2:
            return EvidenceResult(False, "repeated_class_requires_two_refs")
        reason = redact_evidence_reason(str(item.get("reason", "")))
        if reason is None:
            return EvidenceResult(False, "sensitive_evidence")
        normalized.append({"kind": item["kind"], "message_refs": list(unique_refs), "reason": reason})
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return EvidenceResult(True, normalized=tuple(normalized), digest="sha256:" + hashlib.sha256(encoded).hexdigest())


def redact_evidence_reason(reason: str) -> str | None:
    cleaned = "".join(char for char in reason if ord(char) >= 32).strip()
    if _SECRET_RE.search(cleaned):
        return None
    return cleaned[:500]


def find_possible_duplicates(
    operation: Mapping[str, Any], active: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    name = operation.get("name")
    return [
        {"id": item.get("id"), "reason": "same_target"}
        for item in active
        if item.get("target", {}).get("name") == name and item.get("fingerprint") != operation.get("fingerprint")
    ]
