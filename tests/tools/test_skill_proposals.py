import json
import threading
from dataclasses import replace

import pytest

from tools import skill_learning_config, write_approval
from tools.skill_proposals import (
    claim_skill_proposal,
    create_skill_proposal,
    finish_skill_proposal,
    get_skill_proposal_queue_state,
    list_skill_proposals,
    proposal_fingerprint,
    read_skill_proposal_records,
)


def _record(fingerprint: str, *, evidence_ref: int = 1, name: str = "energy-report",
            action: str = "patch"):
    return {
        "schema_version": 2,
        "id": "skp_test",
        "status": "pending",
        "revision": 1,
        "created_at": 1_000.0,
        "updated_at": 1_000.0,
        "expires_at": 1_000.0 + 14 * 86400,
        "target": {"name": name},
        "operation": {
            "action": action,
            "name": name,
            "file_path": "SKILL.md",
            "anchor_key": "sha256:" + "a" * 64,
        },
        "evidence": [{"kind": "user_correction", "message_refs": [evidence_ref]}],
        "provenance": {"origin": "background_review", "review_run_id": "review-1"},
        "fingerprint": fingerprint,
        "base_hash": "sha256:" + "a" * 64,
        "review_hash": "sha256:" + "b" * 64,
        "review_snapshot_digest": "sha256:" + "d" * 64,
    }


def test_same_fingerprint_merges_evidence_and_bumps_revision(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    fp = proposal_fingerprint({
        "action": "patch",
        "name": "energy-report",
        "file_path": "SKILL.md",
        "base_hash": "sha256:" + "a" * 64,
        "result_digest": "sha256:" + "c" * 64,
    })

    first = create_skill_proposal(_record(fp, evidence_ref=1), now=1_000.0)
    second = create_skill_proposal(_record(fp, evidence_ref=2), now=1_001.0)

    assert first.status == "created"
    assert second.status == "merged"
    assert second.proposal["revision"] == 2
    assert second.proposal["evidence"][-1]["message_refs"] == [2]


def test_same_fingerprint_merges_without_consuming_a_full_queue_slot(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    baseline = skill_learning_config.get_skill_learning_config()
    monkeypatch.setattr(
        "tools.skill_proposals.get_skill_learning_config",
        lambda: replace(
            baseline,
            max_pending=1,
            max_pending_per_target=1,
            max_pending_per_anchor=1,
        ),
    )
    fp = proposal_fingerprint({
        "action": "create",
        "name": "energy-report",
        "file_path": "SKILL.md",
        "base_hash": "absent",
        "result_digest": "sha256:" + "c" * 64,
    })

    assert create_skill_proposal(_record(fp, evidence_ref=1), now=1_000.0).status == "created"
    assert create_skill_proposal(_record(fp, evidence_ref=2), now=1_001.0).status == "merged"
    assert create_skill_proposal(
        _record("sha256:" + "e" * 64, evidence_ref=3), now=1_002.0
    ).status == "profile_full"


def test_claim_has_one_winner_and_expired_lease_recovers(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    created = create_skill_proposal(_record("sha256:" + "f" * 64), now=1_000.0)
    pid = created.proposal["id"]
    winners = []

    def claim(owner):
        got = claim_skill_proposal(pid, owner=owner, lease_seconds=5, now=1_001.0)
        if got is not None:
            winners.append(owner)

    threads = [threading.Thread(target=claim, args=(f"w{i}",)) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert winners == [winners[0]]
    assert len(winners) == 1
    assert claim_skill_proposal(pid, owner="late", now=1_007.0)["claimed_by"] == "late"


@pytest.mark.parametrize("fingerprint", [
    "f" * 64,
    "sha256:" + "F" * 64,
    "sha256:" + "f" * 63,
    "md5:" + "f" * 64,
])
def test_malformed_fingerprint_is_rejected_without_writing(
    tmp_path, monkeypatch, fingerprint
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    result = create_skill_proposal(_record(fingerprint), now=1_000.0)

    assert result.status == "invalid_proposal"
    assert list_skill_proposals(now=1_000.0) == []


def test_expired_v1_is_virtual_and_never_rewritten(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    pending_dir = tmp_path / "pending" / "skills"
    pending_dir.mkdir(parents=True)
    legacy_path = pending_dir / "legacy1.json"
    original = (
        '{"id":"legacy1","subsystem":"skills","action":"create",'
        '"summary":"old","origin":"background_review","created_at":1000.0,'
        '"payload":{"action":"create","name":"old"}}'
    )
    legacy_path.write_text(original, encoding="utf-8")

    assert read_skill_proposal_records(status="pending", now=1000.0 + 14 * 86400) == []
    expired = read_skill_proposal_records(status="expired", now=1000.0 + 14 * 86400)
    assert expired[0]["schema_version"] == 1
    assert expired[0]["status"] == "expired"
    assert legacy_path.read_text(encoding="utf-8") == original
    assert get_skill_proposal_queue_state(now=1000.0 + 14 * 86400)["pending_count"] == 0


def test_over_limit_v1_queue_stays_readable_and_blocks_new_v2(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    pending_dir = tmp_path / "pending" / "skills"
    pending_dir.mkdir(parents=True)
    now = 1000.0
    for index in range(26):
        (pending_dir / f"legacy{index}.json").write_text(
            f'{{"id":"legacy{index}","subsystem":"skills","action":"create",'
            '"summary":"old","origin":"background_review","created_at":1000.0,'
            f'"payload":{{"action":"create","name":"old-{index}"}}}}',
            encoding="utf-8",
        )

    state = get_skill_proposal_queue_state(now=now)
    assert state["pending_count"] == 26
    assert state["over_limit"] is True
    assert state["earliest_expires_at"] == 1000.0 + 14 * 86400
    assert len(list_skill_proposals(now=now)) == 26

    result = create_skill_proposal(
        _record(proposal_fingerprint({
            "action": "create",
            "name": "new",
            "file_path": "SKILL.md",
            "base_hash": "absent",
            "result_digest": "sha256:" + "c" * 64,
        }), evidence_ref=9),
        now=now,
    )
    assert result.status == "profile_full"
    assert len(list(pending_dir.glob("legacy*.json"))) == 26


def test_caps_reject_without_replacing_existing_records(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    baseline = skill_learning_config.get_skill_learning_config()
    monkeypatch.setattr(
        "tools.skill_proposals.get_skill_learning_config",
        lambda: replace(baseline, max_pending=2, max_pending_per_target=1),
    )
    first = create_skill_proposal(
        _record("sha256:" + "1" * 64, name="one"), now=1_000.0
    )
    second = create_skill_proposal(
        _record("sha256:" + "2" * 64, name="one", action="create"), now=1_001.0
    )
    assert first.status == "created"
    assert second.status == "target_full"

    monkeypatch.setattr(
        "tools.skill_proposals.get_skill_learning_config",
        lambda: replace(baseline, max_pending=25, max_pending_per_target=5),
    )
    occupied = create_skill_proposal(
        _record("sha256:" + "3" * 64, name="two"), now=1_002.0
    )
    assert occupied.status == "created"
    duplicate_anchor = create_skill_proposal(
        _record("sha256:" + "4" * 64, name="two"), now=1_003.0
    )
    assert duplicate_anchor.status == "anchor_occupied"
    stored = read_skill_proposal_records(status="pending", now=1_003.0)
    assert [item["fingerprint"] for item in stored if item["target"]["name"] == "two"] == [
        "sha256:" + "3" * 64
    ]


def test_v1_and_v2_helpers_do_not_delete_each_other(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    write_approval.stage_write(
        write_approval.SKILLS,
        {"action": "create", "name": "legacy"},
        summary="legacy",
        origin="foreground",
    )
    created = create_skill_proposal(_record("sha256:" + "5" * 64), now=1_000.0)
    v2_id = created.proposal["id"]

    assert all("schema_version" not in item for item in write_approval.list_pending("skills"))
    assert write_approval.get_pending("skills", v2_id) is None
    assert write_approval.discard_pending("skills", v2_id) is False
    assert write_approval.pending_count("skills") == 1
    records = read_skill_proposal_records(status="pending", now=1_000.0)
    legacy = next(item for item in records if item["schema_version"] == 1)
    assert legacy["id"] != v2_id
    assert (tmp_path / "pending" / "skills" / f"{v2_id}.json").exists()


def test_broken_json_is_counted_and_terminal_transitions_are_stable(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    pending = tmp_path / "pending" / "skills"
    pending.mkdir(parents=True)
    (pending / "broken.json").write_text("{", encoding="utf-8")
    created = create_skill_proposal(_record("sha256:" + "6" * 64), now=1_000.0)
    pid = created.proposal["id"]

    state = get_skill_proposal_queue_state(now=1_000.0)
    assert state["broken_count"] == 1
    finished = finish_skill_proposal(
        pid, status="applied", review_hash="sha256:" + "b" * 64, now=1_001.0
    )
    repeated = finish_skill_proposal(
        pid, status="applied", review_hash="sha256:" + "b" * 64, now=1_002.0
    )
    assert finished["status"] == "applied"
    assert repeated["status"] == "applied"
    history = json.loads((tmp_path / "pending" / "skills" / ".history" / f"{pid}.json").read_text())
    assert history["status"] == "applied"
