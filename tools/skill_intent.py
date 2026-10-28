"""Structured trust context for skill writes."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
from contextvars import ContextVar, Token
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path


class SkillWriteIntent(Enum):
    NORMAL = "normal"
    USER_LEARN = "user_learn"
    BACKGROUND_REVIEW = "background_review"


@dataclass(frozen=True, slots=True)
class SkillWriteIntentContext:
    intent: SkillWriteIntent
    origin: str
    attended: bool
    task_id: str
    session_id: str
    review_run_id: str | None
    review_message_refs: frozenset[int]
    review_snapshot_digest: str | None

    def with_intent(self, intent: SkillWriteIntent) -> SkillWriteIntentContext:
        return replace(self, intent=intent)


def normal_skill_context(
    *,
    task_id: str = "",
    session_id: str = "",
    attended: bool = True,
) -> SkillWriteIntentContext:
    return SkillWriteIntentContext(
        intent=SkillWriteIntent.NORMAL,
        origin="foreground",
        attended=attended,
        task_id=task_id,
        session_id=session_id,
        review_run_id=None,
        review_message_refs=frozenset(),
        review_snapshot_digest=None,
    )


_SKILL_WRITE_CONTEXT: ContextVar[SkillWriteIntentContext] = ContextVar(
    "hermes_skill_write_context"
)
_ABSENT = object()
_PROXY_TTL_SECONDS = 60.0
_PROXY_FIELDS = ("iat", "message_sha256", "nonce", "session_id", "v")
_NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")


def current_skill_write_context() -> SkillWriteIntentContext:
    value = _SKILL_WRITE_CONTEXT.get(_ABSENT)
    if value is _ABSENT:
        return normal_skill_context()
    return value


def has_skill_write_context() -> bool:
    return _SKILL_WRITE_CONTEXT.get(_ABSENT) is not _ABSENT


def bind_skill_write_context(context: SkillWriteIntentContext) -> Token:
    if not isinstance(context, SkillWriteIntentContext):
        raise TypeError("skill write context must be SkillWriteIntentContext")
    return _SKILL_WRITE_CONTEXT.set(context)


def reset_skill_write_context(token: Token) -> None:
    _SKILL_WRITE_CONTEXT.reset(token)


def sign_proxy_skill_intent(*, secret: str, session_id: str, message: str, now: float) -> str:
    """Sign a one-minute USER_LEARN envelope. The nonce is claimed on consume."""
    body = {
        "v": 1,
        "iat": now,
        "nonce": secrets.token_hex(16),
        "session_id": session_id,
        "message_sha256": _sha256_text(message),
    }
    envelope = dict(body)
    envelope["sig"] = _proxy_signature(secret, body)
    return json.dumps(envelope, sort_keys=True, separators=(",", ":"))


def consume_proxy_skill_intent(
    envelope,
    *,
    secret: str,
    session_id: str,
    message: str,
    now: float,
    nonce_dir=None,
) -> SkillWriteIntentContext | None:
    """Upgrade to USER_LEARN only when the HMAC, bindings, TTL, and nonce all match."""
    body = _verified_proxy_body(envelope, secret)
    if body is None or not _proxy_bindings_match(
        body, session_id=session_id, message=message, now=now
    ):
        return None
    if not _claim_proxy_nonce(body["nonce"], nonce_dir):
        return None
    return normal_skill_context(session_id=session_id).with_intent(SkillWriteIntent.USER_LEARN)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_proxy_body(body: dict) -> bytes:
    return json.dumps(
        {key: body[key] for key in _PROXY_FIELDS}, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _proxy_signature(secret: str, body: dict) -> str:
    if not isinstance(secret, str):
        raise TypeError("proxy secret must be str")
    return hmac.new(secret.encode("utf-8"), _canonical_proxy_body(body), hashlib.sha256).hexdigest()


def _verified_proxy_body(envelope, secret: str) -> dict | None:
    if not isinstance(envelope, str) or not isinstance(secret, str):
        return None
    try:
        payload = json.loads(envelope)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict) or set(payload) != set(_PROXY_FIELDS) | {"sig"}:
        return None
    signature = payload.get("sig")
    body = {key: payload[key] for key in _PROXY_FIELDS}
    if not isinstance(signature, str):
        return None
    expected = _proxy_signature(secret, body)
    if len(signature) != len(expected) or not hmac.compare_digest(signature, expected):
        return None
    return body


def _proxy_bindings_match(body: dict, *, session_id: str, message: str, now: float) -> bool:
    issued_at = _timestamp(body.get("iat"))
    checked_at = _timestamp(now)
    if issued_at is None or checked_at is None:
        return False
    age = checked_at - issued_at
    if age < 0 or age > _PROXY_TTL_SECONDS:
        return False
    if type(body.get("v")) is not int or body["v"] != 1:
        return False
    return _digest_matches(body.get("session_id"), session_id) and _digest_matches(
        body.get("message_sha256"), message, already_digest=True
    )


def _timestamp(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _digest_matches(stored, material: str, *, already_digest: bool = False) -> bool:
    if not isinstance(stored, str) or not isinstance(material, str):
        return False
    expected = stored if already_digest else _sha256_text(stored)
    actual = _sha256_text(material)
    if len(expected) != len(actual):
        return False
    return hmac.compare_digest(expected, actual)


def _claim_proxy_nonce(nonce, nonce_dir) -> bool:
    if not isinstance(nonce, str) or _NONCE_RE.fullmatch(nonce) is None:
        return False
    try:
        directory = _intent_nonce_dir(nonce_dir)
        directory.mkdir(parents=True, exist_ok=True)
        fd = os.open(directory / nonce, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return False
    except OSError:
        return False
    os.close(fd)
    return True


def _intent_nonce_dir(nonce_dir) -> Path:
    if nonce_dir is not None:
        return Path(nonce_dir)
    from hermes_constants import get_hermes_home

    return get_hermes_home() / "pending" / "skills" / ".intent-nonces"
