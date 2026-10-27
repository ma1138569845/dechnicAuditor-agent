import hashlib
import json
import socket
from pathlib import Path

from tools.skill_health import build_skill_health_report


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _write_skill(root: Path, name: str, body: str = "Use it.") -> Path:
    skill = root / "skills" / name
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Use when testing {name}.\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return skill


def test_audit_is_byte_for_byte_read_only_and_never_opens_network(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    _write_skill(tmp_path, "audit-report", body="TOP_SECRET_SKILL_BODY")
    before = _tree_digest(tmp_path)

    def _network_forbidden(*args, **kwargs):
        raise AssertionError("health audit attempted network access")

    monkeypatch.setattr(socket.socket, "connect", _network_forbidden)
    report = build_skill_health_report(days=30, now=1_800_000_000.0)

    assert report["library"]["total"] == 1
    assert "TOP_SECRET_SKILL_BODY" not in json.dumps(report)
    assert _tree_digest(tmp_path) == before


def test_insufficient_usage_is_review_not_stale(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    _write_skill(tmp_path, "audit-report")

    report = build_skill_health_report(days=30, now=1_800_000_000.0)

    row = report["recommendations"][0]
    assert row["status"] == "REVIEW"
    assert "usage_evidence_incomplete" in row["reasons"]
    assert report["evidence_complete"] is False


def test_stale_is_only_a_recommendation(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setattr(
        "tools.skill_health.curator_archive_after_days",
        lambda: 30,
    )
    monkeypatch.setattr(
        "tools.skill_health.load_usage",
        lambda: {
            "audit-report": {
                "created_by": "agent",
                "state": "active",
                "created_at": "2025-01-01T00:00:00+00:00",
                "last_used_at": None,
                "last_viewed_at": None,
                "use_count": 0,
                "view_count": 0,
                "pinned": False,
            }
        },
    )
    _write_skill(tmp_path, "audit-report")
    before = _tree_digest(tmp_path)

    report = build_skill_health_report(days=30, now=1_800_000_000.0)

    assert report["recommendations"][0]["status"] == "STALE"
    assert _tree_digest(tmp_path) == before


def test_duplicate_paths_and_unreadable_skills_are_broken_not_repaired(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    skills = tmp_path / "skills"
    skills.mkdir()
    path = _write_skill(tmp_path, "audit-report") / "SKILL.md"
    before = _tree_digest(tmp_path)
    catalog = [
        {
            "name": "audit-report",
            "load_name": "audit-report",
            "path": path,
            "root": skills,
            "tier": 0,
            "status": "unique",
        },
        {
            "name": "audit-report",
            "load_name": "audit-report-copy",
            "path": path,
            "root": skills,
            "tier": 0,
            "status": "ambiguous",
        },
    ]
    monkeypatch.setattr(
        "tools.skill_health._skill_catalog_snapshot",
        lambda: (catalog, [path], set()),
    )

    report = build_skill_health_report(days=30, now=1_800_000_000.0)

    assert report["library"]["broken"] == 2
    assert {row["status"] for row in report["recommendations"]} == {"BROKEN"}
    assert all("duplicate_discovery_path" in row["reasons"] for row in report["recommendations"])
    assert _tree_digest(tmp_path) == before


def test_protected_skills_keep_with_bounded_reasons(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    skills = tmp_path / "skills"
    skills.mkdir()
    paths = []
    names = (
        "pinned-skill",
        "cron-skill",
        "user-skill",
        "hub-skill",
        "external-skill",
        "modified-skill",
    )
    for name in names:
        paths.append(_write_skill(tmp_path, name) / "SKILL.md")
    catalog = [
        {
            "name": path.parent.name,
            "load_name": path.parent.name,
            "path": path,
            "root": skills,
            "tier": 0,
            "status": "unique",
        }
        for path in paths
    ]
    monkeypatch.setattr(
        "tools.skill_health._skill_catalog_snapshot",
        lambda: (catalog, paths, set()),
    )
    monkeypatch.setattr(
        "tools.skill_health.load_usage",
        lambda: {
            "pinned-skill": {"pinned": True, "created_by": "agent"},
            "cron-skill": {"created_by": "agent"},
            "user-skill": {"created_by": "learn"},
            "hub-skill": {"created_by": "agent"},
            "external-skill": {"created_by": "agent"},
            "modified-skill": {"created_by": "agent"},
        },
    )
    monkeypatch.setattr(
        "tools.skill_health._cron_referenced_skill_names",
        lambda: {"cron-skill"},
    )
    monkeypatch.setattr(
        "tools.skill_health._hub_installed_skill_names",
        lambda: {"hub-skill"},
    )
    monkeypatch.setattr(
        "tools.skill_health._external_skill_names",
        lambda: {"external-skill"},
    )
    monkeypatch.setattr(
        "tools.skill_health._modified_skill_names",
        lambda: {"modified-skill"},
    )

    report = build_skill_health_report(days=30, now=1_800_000_000.0)

    assert {row["skill"]: row["status"] for row in report["recommendations"]} == {
        "pinned-skill": "KEEP",
        "cron-skill": "KEEP",
        "user-skill": "KEEP",
        "hub-skill": "KEEP",
        "external-skill": "KEEP",
        "modified-skill": "KEEP",
    }
    assert all(set(row["reasons"]).issubset({
        "cron_referenced",
        "external_skill",
        "hub_skill",
        "modified_skill",
        "pinned",
        "user_owned",
    }) for row in report["recommendations"])
