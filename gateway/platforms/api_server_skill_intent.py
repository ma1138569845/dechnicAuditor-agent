"""Authenticated proxy envelopes that may upgrade one API turn to USER_LEARN."""

from __future__ import annotations

import hmac
import time
from typing import Any

from gateway.platforms._shared import get_scoped_secret


def add_proxy_skill_write_context(
    adapter,
    request,
    run_kwargs: dict[str, Any],
    *,
    session_id: str,
    message: str,
    now: float | None = None,
) -> None:
    """Add a verified context in place; missing or invalid proof leaves the turn NORMAL."""
    envelope = request.headers.get("X-Hermes-Skill-Intent", "")
    expected = adapter._expected_api_key()
    auth = request.headers.get("Authorization", "")
    if not envelope or not expected or not auth.startswith("Bearer "):
        return
    token = auth[7:].strip()
    if not token or not hmac.compare_digest(token.encode(), expected.encode()):
        return
    proxy_key = str(get_scoped_secret("GATEWAY_PROXY_KEY", "") or "").strip()
    if not proxy_key:
        return
    from tools.skill_intent import consume_proxy_skill_intent

    context = consume_proxy_skill_intent(
        envelope,
        secret=proxy_key,
        session_id=session_id,
        message=message,
        now=time.time() if now is None else now,
    )
    if context is not None:
        run_kwargs["skill_write_context"] = context
