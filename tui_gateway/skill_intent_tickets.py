"""In-memory, single-use tickets that bind a slash dispatch to one prompt submit."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from dataclasses import dataclass

from tools.skill_intent import SkillWriteIntent, SkillWriteIntentContext, normal_skill_context


@dataclass(frozen=True, slots=True)
class _Ticket:
    ticket_digest: str
    session_digest: str
    profile_digest: str
    message_digest: str
    intent: SkillWriteIntent
    expires_at: float


class DispatcherIntentTicketStore:
    """60-second tickets scoped to one runtime session, profile, and message."""

    def __init__(self, ttl_seconds: float = 60, clock=time.time):
        self._ttl_seconds = float(ttl_seconds)
        self._clock = clock
        self._lock = threading.Lock()
        self._tickets: dict[str, _Ticket] = {}

    def issue(self, session_id: str, profile: str, message: str, intent: SkillWriteIntent) -> str:
        if not isinstance(intent, SkillWriteIntent):
            raise TypeError("ticket intent must be SkillWriteIntent")
        ticket = secrets.token_urlsafe(32)
        digest = _digest(ticket)
        record = _Ticket(
            ticket_digest=digest,
            session_digest=_digest(session_id),
            profile_digest=_digest(profile),
            message_digest=_digest(message),
            intent=intent,
            expires_at=float(self._clock()) + self._ttl_seconds,
        )
        with self._lock:
            self._tickets[digest] = record
        return ticket

    def consume(
        self, ticket: str, session_id: str, profile: str, message: str
    ) -> SkillWriteIntentContext | None:
        presented = _digest(ticket)
        with self._lock:
            record = self._tickets.get(presented)
            if record is None or not hmac.compare_digest(record.ticket_digest, presented):
                return None
            if float(self._clock()) > record.expires_at:
                self._tickets.pop(presented, None)
                return None
            if not _same(record.session_digest, _digest(session_id)):
                return None
            if not _same(record.profile_digest, _digest(profile)):
                return None
            if not _same(record.message_digest, _digest(message)):
                return None
            del self._tickets[presented]
        return normal_skill_context(session_id=str(session_id)).with_intent(record.intent)


def _digest(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _same(stored: str, presented: str) -> bool:
    return hmac.compare_digest(stored, presented)


ticket_store = DispatcherIntentTicketStore()


def resolve_ticket_profile(params: dict, session: dict) -> str:
    """Use the request override first, then the session home's canonical profile name."""
    explicit = str(params.get("profile") or "").strip()
    if explicit:
        return explicit
    from hermes_constants import profile_name_for_home

    return profile_name_for_home(session.get("profile_home")) or "default"
