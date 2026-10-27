import json
import queue
from types import SimpleNamespace

from tools.skill_intent import SkillWriteIntent, consume_proxy_skill_intent, sign_proxy_skill_intent
from tools.skill_intent_queue import QueuedSkillIntentPrompt
from tui_gateway.skill_intent_tickets import DispatcherIntentTicketStore


def test_ticket_is_bound_to_message_session_and_profile(tmp_path):
    store = DispatcherIntentTicketStore(ttl_seconds=60, clock=lambda: 100.0)
    ticket = store.issue(
        "runtime-1", "default", "expanded learn prompt", SkillWriteIntent.USER_LEARN
    )

    assert store.consume(ticket, "runtime-1", "default", "changed") is None
    assert store.consume(ticket, "other", "default", "expanded learn prompt") is None
    assert store.consume(ticket, "runtime-1", "other", "expanded learn prompt") is None
    accepted = store.consume(ticket, "runtime-1", "default", "expanded learn prompt")
    assert accepted.intent is SkillWriteIntent.USER_LEARN
    assert store.consume(ticket, "runtime-1", "default", "expanded learn prompt") is None


def test_expired_ticket_is_not_trusted():
    now = {"t": 100.0}
    store = DispatcherIntentTicketStore(ttl_seconds=60, clock=lambda: now["t"])
    ticket = store.issue(
        "runtime-1", "default", "expanded learn prompt", SkillWriteIntent.USER_LEARN
    )

    now["t"] = 160.1
    assert store.consume(ticket, "runtime-1", "default", "expanded learn prompt") is None


def test_proxy_envelope_is_single_use_and_never_trusts_bare_json(tmp_path):
    secret = "s" * 32
    envelope = sign_proxy_skill_intent(
        secret=secret,
        session_id="session-1",
        message="expanded learn prompt",
        now=100.0,
    )
    nonce_dir = tmp_path / "nonces"

    first = consume_proxy_skill_intent(
        envelope, secret=secret, session_id="session-1",
        message="expanded learn prompt", now=101.0, nonce_dir=nonce_dir,
    )
    replay = consume_proxy_skill_intent(
        envelope, secret=secret, session_id="session-1",
        message="expanded learn prompt", now=102.0, nonce_dir=nonce_dir,
    )

    assert first.intent is SkillWriteIntent.USER_LEARN
    assert replay is None
    assert consume_proxy_skill_intent(
        '{"skill_write_intent":"user_learn"}', secret=secret, session_id="session-1",
        message="expanded learn prompt", now=101.0, nonce_dir=nonce_dir,
    ) is None


def test_bad_proxy_signature_and_wrong_session_do_not_burn_the_nonce(tmp_path):
    secret = "s" * 32
    envelope = sign_proxy_skill_intent(
        secret=secret,
        session_id="session-1",
        message="expanded learn prompt",
        now=100.0,
    )
    payload = json.loads(envelope)
    payload["sig"] = "0" * 64 if not str(payload["sig"]).startswith("0") else "1" * 64
    forged = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    nonce_dir = tmp_path / "nonces"
    kwargs = {
        "secret": secret,
        "message": "expanded learn prompt",
        "now": 101.0,
        "nonce_dir": nonce_dir,
    }

    assert consume_proxy_skill_intent(forged, session_id="session-1", **kwargs) is None
    assert consume_proxy_skill_intent(envelope, session_id="other-session", **kwargs) is None
    accepted = consume_proxy_skill_intent(envelope, session_id="session-1", **kwargs)

    assert accepted.intent is SkillWriteIntent.USER_LEARN


def test_omitted_nonce_dir_is_profile_local_and_single_use(monkeypatch, tmp_path):
    home = tmp_path / "hermes-home"
    monkeypatch.setattr("hermes_constants.get_hermes_home", lambda: home)
    secret = "s" * 32
    envelope = sign_proxy_skill_intent(
        secret=secret,
        session_id="session-1",
        message="expanded learn prompt",
        now=100.0,
    )

    first = consume_proxy_skill_intent(
        envelope, secret=secret, session_id="session-1",
        message="expanded learn prompt", now=101.0, nonce_dir=None,
    )
    replay = consume_proxy_skill_intent(
        envelope, secret=secret, session_id="session-1",
        message="expanded learn prompt", now=102.0, nonce_dir=None,
    )

    nonce_dir = home / "pending" / "skills" / ".intent-nonces"
    assert first.intent is SkillWriteIntent.USER_LEARN
    assert replay is None
    assert nonce_dir.is_dir()
    assert any(nonce_dir.iterdir())


def test_cli_learn_handler_is_the_only_prompt_queue_producer_of_learn_intent(monkeypatch):
    from hermes_cli import cli_commands_mixin

    cli_commands_mixin._t = lambda key, **_kwargs: key
    cli = cli_commands_mixin.CLICommandsMixin()
    queued = []
    cli._queue_prompt_turn = lambda msg, command, ack="": queued.append((msg, command))

    cli._handle_learn_command("/learn keep the audit checks")
    cli._handle_plan_command("/plan outline a task")

    assert isinstance(queued[0][0], QueuedSkillIntentPrompt)
    assert queued[0][0].intent is SkillWriteIntent.USER_LEARN
    assert queued[1][1] == "/plan"
    assert isinstance(queued[1][0], str)


def test_generic_cli_prompt_queue_does_not_infer_intent_from_its_command_text():
    from hermes_cli.cli_commands_mixin import CLICommandsMixin

    cli = CLICommandsMixin()
    cli._pending_input = queue.Queue()

    cli._queue_prompt_turn("ordinary expanded prompt", "/learn")

    assert cli._pending_input.get_nowait() == "ordinary expanded prompt"


def test_cli_unwraps_learn_context_for_the_turn_without_shared_pending_state():
    from hermes_cli.cli_process_notifications import CLIProcessNotificationsMixin

    node = CLIProcessNotificationsMixin()
    prompt = QueuedSkillIntentPrompt("expanded learn prompt", SkillWriteIntent.USER_LEARN)

    text, voice, seeded, context = node._tui_unwrap_input(prompt)

    assert (text, voice, seeded) == ("expanded learn prompt", False, False)
    assert context.intent is SkillWriteIntent.USER_LEARN
    assert not hasattr(node, "_pending_skill_write_context")


def test_tui_command_dispatch_issues_a_bound_learn_ticket(monkeypatch):
    from tui_gateway import methods_tools

    monkeypatch.setattr(
        methods_tools,
        "_ok",
        lambda rid, payload: {"jsonrpc": "2.0", "id": rid, "result": payload},
        raising=False,
    )
    monkeypatch.setattr(
        "agent.learn_prompt.build_learn_prompt", lambda arg: f"expanded learn: {arg}"
    )
    response = methods_tools._cmd_learn(
        "request-1",
        {"profile": "work", "session_id": "runtime-1"},
        {"session_key": "runtime-1"},
        "learn",
        "keep this",
    )
    payload = response["result"]

    assert payload["type"] == "send"
    assert payload["skill_intent_ticket"]
    from tui_gateway.skill_intent_tickets import ticket_store

    assert ticket_store.consume(
        payload["skill_intent_ticket"], "runtime-1", "work", "expanded learn: keep this"
    ).intent is SkillWriteIntent.USER_LEARN

    plan = methods_tools._cmd_plan(
        "request-2", {"profile": "work", "session_id": "runtime-1"}, {}, "plan", "outline"
    )
    assert "skill_intent_ticket" not in plan["result"]


def test_api_proxy_requires_bearer_auth_and_the_separate_proxy_signing_key(monkeypatch):
    from gateway.config import PlatformConfig
    from gateway.platforms import api_server
    from gateway.platforms import api_server_skill_intent
    from gateway.platforms.api_server_skill_intent import add_proxy_skill_write_context

    api_key = "a" * 32
    proxy_key = "p" * 32
    monkeypatch.setattr(
        api_server,
        "_get_scoped_secret",
        lambda name, default="": (
            proxy_key
            if name == "GATEWAY_PROXY_KEY"
            else api_key
            if name == "API_SERVER_KEY"
            else default
        ),
    )
    monkeypatch.setattr(
        api_server_skill_intent,
        "get_scoped_secret",
        lambda name, default="": proxy_key if name == "GATEWAY_PROXY_KEY" else default,
    )
    adapter = api_server.APIServerAdapter(
        PlatformConfig(enabled=True, extra={"key": api_key})
    )
    envelope = sign_proxy_skill_intent(
        secret=proxy_key,
        session_id="session-1",
        message="expanded learn prompt",
        now=100.0,
    )
    request = SimpleNamespace(
        headers={
            "Authorization": f"Bearer {api_key}",
            "X-Hermes-Skill-Intent": envelope,
        }
    )

    accepted_params = {}
    add_proxy_skill_write_context(
        adapter,
        request,
        accepted_params,
        session_id="session-1",
        message="expanded learn prompt",
        now=101.0,
    )
    replay_params = {}
    add_proxy_skill_write_context(
        adapter,
        request,
        replay_params,
        session_id="session-1",
        message="expanded learn prompt",
        now=102.0,
    )
    wrong_secret = sign_proxy_skill_intent(
        secret=api_key,
        session_id="session-1",
        message="expanded learn prompt",
        now=103.0,
    )
    forged = SimpleNamespace(
        headers={
            "Authorization": f"Bearer {api_key}",
            "X-Hermes-Skill-Intent": wrong_secret,
        }
    )

    assert accepted_params["skill_write_context"].intent is SkillWriteIntent.USER_LEARN
    assert replay_params == {}
    forged_params = {}
    add_proxy_skill_write_context(
        adapter,
        forged,
        forged_params,
        session_id="session-1",
        message="expanded learn prompt",
        now=104.0,
    )
    assert forged_params == {}


def test_gateway_learn_marks_only_a_successfully_rewritten_dispatcher_turn():
    import asyncio
    from gateway.platforms.event import MessageEvent
    from gateway.run_inbound import GatewayInboundMixin

    class Gateway(GatewayInboundMixin):
        async def _send_command_ack(self, *_args):
            return None

        async def _hm_rewrite_turn_to_prompt(self, event, *_args):
            event.text = "expanded learn prompt"
            return False, None

    event = MessageEvent(text="/learn keep the audit checks")
    result = asyncio.run(Gateway()._hm_cmd_learn(event, None, "session"))

    assert result == (False, None)
    assert event.skill_write_intent == "user_learn"
    assert event.text == "expanded learn prompt"

    pasted = MessageEvent(text="[/learn] pasted instructions")
    assert pasted.skill_write_intent is None

    class FailingGateway(Gateway):
        async def _hm_rewrite_turn_to_prompt(self, *_args):
            return True, "failed"

    failed = MessageEvent(text="/learn keep the audit checks")
    assert asyncio.run(FailingGateway()._hm_cmd_learn(failed, None, "session")) == (
        True,
        "failed",
    )
    assert failed.skill_write_intent is None
