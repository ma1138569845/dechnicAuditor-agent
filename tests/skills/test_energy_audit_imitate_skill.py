"""Tests for the energy-audit-imitate skill."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = REPO_ROOT / "skills" / "productivity" / "energy-audit-imitate"
SKILL_PATH = SKILL_DIR / "SKILL.md"
SCRIPT_PATH = SKILL_DIR / "scripts" / "assemble_report.py"


def _frontmatter_and_body():
    content = SKILL_PATH.read_text(encoding="utf-8")
    assert content.startswith("---")
    m = re.search(r"\n---\s*\n", content[3:])
    assert m, "frontmatter must close with ---"
    fm = yaml.safe_load(content[3 : m.start() + 3])
    body = content[m.end() + 3 :]
    return fm, body


def test_skill_file_exists():
    assert SKILL_PATH.is_file()
    assert (SKILL_DIR / "references" / "chapter-outlines.md").is_file()
    assert (SKILL_DIR / "references" / "report-format-spec.md").is_file()
    assert SCRIPT_PATH.is_file()
    assert (SKILL_DIR / "scripts" / "add_watermark.py").is_file()


def test_frontmatter_required_fields():
    fm, _ = _frontmatter_and_body()
    for field in ("name", "description", "version", "author", "license", "platforms"):
        assert field in fm, f"missing frontmatter field: {field}"
    assert fm["name"] == "energy-audit-imitate"


def test_description_hardline():
    fm, _ = _frontmatter_and_body()
    desc = fm["description"]
    assert len(desc) <= 60, f"description is {len(desc)} chars; hardline is 60"
    assert desc.endswith(".")


def test_author_credits_human_first():
    fm, _ = _frontmatter_and_body()
    assert not str(fm["author"]).startswith("Hermes Agent")


def test_related_skills_resolve_in_repo():
    fm, _ = _frontmatter_and_body()
    for name in fm["metadata"]["hermes"]["related_skills"]:
        hits = (
            list(REPO_ROOT.glob(f"skills/*/{name}/SKILL.md"))
            + list(REPO_ROOT.glob(f"optional-skills/*/{name}/SKILL.md"))
            + list(REPO_ROOT.glob(f"skills/*/*/{name}/SKILL.md"))
        )
        assert hits, f"related_skills entry does not resolve in-repo: {name}"


def test_body_structure_and_size():
    _, body = _frontmatter_and_body()
    for section in ("## When to Use", "## Procedure", "## Pitfalls", "## Verification"):
        assert section in body, f"missing section: {section}"
    assert len(SKILL_PATH.read_text(encoding="utf-8")) <= 100_000


def test_no_machine_local_paths():
    content = SKILL_PATH.read_text(encoding="utf-8")
    assert "/home/" not in content
    assert not re.search(r"[A-Z]:\\\\Users", content)


def test_steps_have_completion_criteria():
    _, body = _frontmatter_and_body()
    steps = re.findall(r"^### \d+\..*?(?=^### \d+\.|^## )", body, re.MULTILINE | re.DOTALL)
    assert len(steps) >= 5
    for step in steps:
        assert "Done when" in step, f"step missing completion criterion: {step[:60]!r}"


def test_agent_path_does_not_call_script_pipeline():
    _, body = _frontmatter_and_body()
    assert "`energy_audit_get_project`" in body
    assert "`energy_audit_rag_search`" in body
    pitfalls = body.split("## Pitfalls", 1)[1].split("## Verification", 1)[0]
    assert "energy_audit_imitate_report" in pitfalls
    procedure = body.split("## Procedure", 1)[1].split("## Pitfalls", 1)[0]
    assert "energy_audit_imitate_report" not in procedure


def test_assemble_spec_requires_all_chapters():
    import importlib.util

    spec = importlib.util.spec_from_file_location("assemble_report", SCRIPT_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    with pytest.raises(ValueError, match="project_name"):
        mod.build_report_data({"imitated_chapters": {f"第{i}章": "x" for i in range(1, 9)}})

    incomplete = {f"第{i}章": "正文" for i in range(1, 8)}
    with pytest.raises(ValueError, match="missing chapter"):
        mod.build_report_data({
            "project_name": "示例单位",
            "audit_type": "公共机构",
            "imitated_chapters": incomplete,
        })

    payload = {
        "project_name": "示例单位",
        "audit_type": "公共机构",
        "imitated_chapters": {f"第{i}章": f"{i}.1 小节\n正文" for i in range(1, 9)},
    }
    data = mod.build_report_data(payload)
    assert data["generation_mode"] == "imitate"
    assert set(data["imitated_chapters"]) == {f"第{i}章" for i in range(1, 9)}
    roundtrip = json.loads(json.dumps(data, ensure_ascii=False))
    assert roundtrip["project_name"] == "示例单位"


def test_format_spec_covers_toc_and_watermark():
    spec = (SKILL_DIR / "references" / "report-format-spec.md").read_text(encoding="utf-8")
    assert "目  录" in spec or "目录" in spec
    assert "水印" in spec
    assert "DrawingML" in spec
    assert "TOC" in spec
    _, body = _frontmatter_and_body()
    assert "`references/report-format-spec.md`" in body


def test_resolve_unit_name_strips_report_suffix():
    import importlib.util

    spec = importlib.util.spec_from_file_location("assemble_report", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.resolve_unit_name({"project_name": "某法院能源审计报告"}) == "某法院"
    assert mod.resolve_unit_name({
        "project_name": "某法院能源审计",
        "unit_name": "烟台经济技术开发区人民法院",
    }) == "烟台经济技术开发区人民法院"
