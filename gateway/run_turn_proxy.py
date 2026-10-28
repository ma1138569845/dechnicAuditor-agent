"""Small, side-effect-free helpers for the remote API proxy turn."""

from __future__ import annotations

import time
from typing import Any, Callable, Optional


def proxy_error_result(text: str) -> dict[str, Any]:
    return {"final_response": text, "messages": [], "api_calls": 0, "tools": []}


def run_still_current_fn(owner, session_key: Optional[str], run_generation: Optional[int]) -> Callable[[], bool]:
    """Predicate: the admitted generation still owns this session key."""
    def still_current() -> bool:
        if run_generation is None or not session_key:
            return True
        return owner._is_session_run_current(session_key, run_generation)

    return still_current


def proxy_skill_intent_headers(
    intent: Optional[str], proxy_key: str, session_id: str, message: str
) -> dict[str, str]:
    """Sign only the dispatcher-owned learn intent, using the proxy credential."""
    if intent != "user_learn" or not proxy_key or not session_id:
        return {}
    from tools.skill_intent import sign_proxy_skill_intent

    return {
        "X-Hermes-Skill-Intent": sign_proxy_skill_intent(
            secret=proxy_key, session_id=session_id, message=message, now=time.time()
        )
    }
