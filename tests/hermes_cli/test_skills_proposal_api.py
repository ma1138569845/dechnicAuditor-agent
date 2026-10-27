from concurrent.futures import ThreadPoolExecutor
import json
import time

from fastapi.testclient import TestClient

from hermes_cli import web_server
from tools.skill_intent import SkillWriteIntent, SkillWriteIntentContext
from tools.skill_proposal_service import submit_skill_proposal


def _client():
    client = TestClient(web_server.app, base_url="http://127.0.0.1")
    client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
    return client


def _context():
    return SkillWriteIntentContext(
        intent=SkillWriteIntent.BACKGROUND_REVIEW,
        origin="background_review",
        attended=False,
        task_id="task-1",
        session_id="session-1",
        review_run_id="review-1",
        review_message_refs=frozenset({2}),
        review_snapshot_digest="sha256:" + "a" * 64,
    )


def _operation(name="audit-report"):
    return {
        "action": "create",
        "name": name,
        "content": (
            f"---\nname: {name}\n"
            "description: Use when writing an audit report.\n---\n\n"
            "Verify sources before writing.\n"
        ),
    }


def _stage(tmp_path, monkeypatch, *, evidence_kind="user_correction", now=1_800_000_000.0):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    return submit_skill_proposal(
        _operation(),
        [
            {
                "kind": evidence_kind,
                "message_refs": [2],
                "reason": "verify sources before writing",
            }
        ],
        _context(),
        now=now,
    )


def _make_other_profile(home):
    other = home / "profiles" / "other"
    other.mkdir(parents=True)
    (other / "config.yaml").write_text("{}\n", encoding="utf-8")


def test_list_and_detail_are_profile_scoped(tmp_path, monkeypatch):
    staged = _stage(tmp_path, monkeypatch)
    _make_other_profile(tmp_path)
    client = _client()

    listed = client.get("/api/skills/proposals?status=pending&profile=default")
    detail = client.get(
        f"/api/skills/proposals/{staged['pending_id']}?profile=default"
    )
    other = client.get("/api/skills/proposals?status=pending&profile=other")

    assert listed.status_code == 200
    assert listed.json()["proposals"][0]["id"] == staged["pending_id"]
    assert detail.status_code == 200
    assert detail.json()["review_hash"] == staged["review_hash"]
    assert other.json()["proposals"] == []
    assert other.json()["queue"]["pending_count"] == 0


def test_approve_payload_rejects_extra_fields(tmp_path, monkeypatch):
    staged = _stage(tmp_path, monkeypatch)
    client = _client()

    response = client.post(
        f"/api/skills/proposals/{staged['pending_id']}/approve?profile=default",
        json={
            "revision": staged["revision"],
            "review_hash": staged["review_hash"],
            "base_hash": staged["base_hash"],
            "fingerprint": "sha256:" + "f" * 64,
        },
    )

    assert response.status_code == 422


def test_stale_review_hash_returns_current_hash_without_writing(
    tmp_path, monkeypatch
):
    first = _stage(tmp_path, monkeypatch)
    submit_skill_proposal(
        _operation(),
        [
            {
                "kind": "user_request",
                "message_refs": [2],
                "reason": "remember this workflow",
            }
        ],
        _context(),
        now=1_800_000_001.0,
    )
    client = _client()

    response = client.post(
        f"/api/skills/proposals/{first['pending_id']}/approve?profile=default",
        json={
            "revision": first["revision"],
            "review_hash": first["review_hash"],
            "base_hash": first["base_hash"],
        },
    )

    body = response.json()
    assert response.status_code == 409
    assert body["error"] == "review_hash_mismatch"
    assert body["current_revision"] == 2
    assert body["current_review_hash"] != first["review_hash"]
    assert not (tmp_path / "skills" / "audit-report").exists()


def test_v2_reject_requires_the_review_hash(tmp_path, monkeypatch):
    staged = _stage(tmp_path, monkeypatch)
    client = _client()

    response = client.post(
        f"/api/skills/proposals/{staged['pending_id']}/reject?profile=default",
        json={},
    )

    assert response.status_code == 422
    assert not (
        tmp_path / "pending" / "skills" / ".history"
        / (staged["pending_id"] + ".json")
    ).exists()


def test_v1_can_be_read_and_rejected_but_never_approved(
    tmp_path, monkeypatch
):
    from tools import write_approval as wa

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    legacy = wa.stage_write(
        wa.SKILLS,
        {
            "action": "create",
            "name": "legacy",
            "content": "---\nname: legacy\ndescription: legacy\n---\n\nUse it.\n",
        },
        summary="legacy pending",
        origin=wa.current_origin(),
    )
    client = _client()

    listed = client.get("/api/skills/proposals?profile=default").json()
    assert listed["proposals"][0]["schema_version"] == 1
    assert client.get(
        f"/api/skills/proposals/{legacy['id']}?profile=default"
    ).status_code == 200
    denied = client.post(
        f"/api/skills/proposals/{legacy['id']}/approve?profile=default",
        json={
            "revision": 1,
            "review_hash": "sha256:" + "a" * 64,
            "base_hash": "sha256:" + "b" * 64,
        },
    )
    assert denied.status_code == 409
    assert denied.json()["error"] == "legacy_pending_requires_explicit_edit"
    assert wa.get_pending(wa.SKILLS, legacy["id"]) is not None

    rejected = client.post(
        f"/api/skills/proposals/{legacy['id']}/reject?profile=default",
        json={},
    )
    assert rejected.status_code == 200
    assert wa.get_pending(wa.SKILLS, legacy["id"]) is None
    assert not (
        tmp_path / "pending" / "skills" / ".history" / f"{legacy['id']}.json"
    ).exists()


def test_concurrent_approval_has_one_winner_and_one_write(
    tmp_path, monkeypatch
):
    staged = _stage(tmp_path, monkeypatch)
    payload = {
        "revision": staged["revision"],
        "review_hash": staged["review_hash"],
        "base_hash": staged["base_hash"],
    }

    def approve():
        return _client().post(
            f"/api/skills/proposals/{staged['pending_id']}/approve?profile=default",
            json=payload,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: approve(), range(2)))

    assert sorted(response.status_code for response in responses) == [200, 409]
    skill_dir = tmp_path / "skills" / "audit-report"
    assert skill_dir.exists()
    assert len(list(skill_dir.rglob("SKILL.md"))) == 1


def test_over_limit_v1_queue_is_visible_without_being_rewritten(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    pending = tmp_path / "pending" / "skills"
    pending.mkdir(parents=True)
    now = time.time()
    paths = []
    for index in range(26):
        path = pending / f"legacy{index}.json"
        path.write_text(
            json.dumps(
                {
                    "id": f"legacy{index}",
                    "subsystem": "skills",
                    "action": "create",
                    "summary": f"legacy {index}",
                    "origin": "background_review",
                    "created_at": now,
                    "payload": {"action": "create", "name": f"legacy-{index}"},
                }
            ),
            encoding="utf-8",
        )
        paths.append(path)
    before = {path: path.read_bytes() for path in paths}
    client = _client()

    listed = client.get("/api/skills/proposals?profile=default")

    assert listed.status_code == 200
    assert listed.json()["count"] == 26
    assert listed.json()["queue"]["over_limit"] is True
    assert {path: path.read_bytes() for path in paths} == before

    blocked = submit_skill_proposal(
        _operation(name="new-proposal"),
        [{"kind": "user_request", "message_refs": [2], "reason": "remember"}],
        _context(),
        now=now,
    )
    assert blocked["error"] == "proposal_inbox_full"
    assert {path: path.read_bytes() for path in paths} == before
