"""章节仿写流水线：结构分析、项目事实裁剪、编排（RAG/LLM 均 mock）。"""

import json

import pytest

from tools.energy_audit.imitate_pipeline import (
    ProjectNotFoundError,
    analyze_paragraph_structure,
    extract_project_facts,
    load_project_data,
    normalize_chapter,
    retrieve_references,
    run_imitate,
)
from tools.energy_audit.project_data import (
    AuditProject,
    BuildingInfo,
    EnergySaving,
    EnergyYearly,
    Equipment,
    ManagementInfo,
    MeteringInfo,
    ProjectBase,
)
from tools.energy_audit_imitate_tool import (
    _handle_imitate_paragraph,
    rest_imitate_energy_audit_paragraph,
)


def _project(**kwargs) -> AuditProject:
    base_kw = dict(
        name="莘县县政府能源审计",
        unit_name="莘县县政府",
        unit_short="县政府",
        address="山东省聊城市莘县",
        unit_type="公共机构",
        institution_category="党政机关",
        specific_type="机关",
        people_count=320,
        building_area=18500.0,
        basic_situation="县政府机关办公区，承担县域行政管理职能。",
        admin_affiliation="莘县人民政府",
    )
    base_kw.update(kwargs.pop("base", {}))
    return AuditProject(
        base=ProjectBase(**base_kw),
        buildings=kwargs.get("buildings") or [
            BuildingInfo(name="主办公楼", area=12000, function="办公", floors="地上6层"),
        ],
        energy_yearly=kwargs.get("energy_yearly") or [
            EnergyYearly(year=2023, electricity_kwh=1_200_000, water_m3=18000),
            EnergyYearly(year=2024, electricity_kwh=1_080_000, water_m3=16500),
        ],
        equipment=kwargs.get("equipment") or [
            Equipment(name="螺杆冷水机组", category="空调", spec="300RT", quantity=2),
        ],
        metering=kwargs.get("metering") or MeteringInfo(
            has_monitoring_system=True, electric_meters=12, water_meters=4,
        ),
        management=kwargs.get("management") or ManagementInfo(
            management_org="成立节能工作领导小组，办公室设在机关事务科。",
            management_policy="坚持节约优先，实行能耗定额考核。",
            honors="获得县级公共机构节能示范单位",
        ),
        energy_saving=kwargs.get("energy_saving") or [
            EnergySaving(statistical_year=2024, energy_management=1, has_awards=1, award_name="县级节能示范"),
        ],
    )


SAMPLE_REF = """
3.1 能源资源管理机构

根据《公共机构节能条例》，山东省人力资源和社会保障厅成立了节能工作领导小组，办公室设在机关服务中心，明确各处室节能管理职责。

3.2 能源资源管理目标和方针

该单位制定了《能源管理制度》，将年度节能目标分解到责任处室，实行季度考核。由表3-1可见近三年节能目标完成情况。

| 年度 | 目标 | 完成情况 |
| 2022 | 下降3% | 完成 |
| 2023 | 下降3% | 完成 |

综上所述，该单位能源管理体系基本健全。
"""


class TestNormalizeChapter:
    def test_arabic_and_cn_aliases(self):
        assert normalize_chapter("3") == ("第3章", "")
        assert normalize_chapter("第3章") == ("第3章", "")
        assert normalize_chapter("第三章") == ("第3章", "")
        assert normalize_chapter("chapter3") == ("第3章", "")

    def test_dotted_section(self):
        assert normalize_chapter("3.1") == ("第3章", "3.1")
        assert normalize_chapter("3.1 机构职责") == ("第3章", "3.1 机构职责")

    def test_chapter_with_trailing_section(self):
        chapter, section = normalize_chapter("第3章", "3.1 机构职责")
        assert chapter == "第3章"
        assert "3.1" in section
        assert "机构职责" in section

    def test_empty(self):
        assert normalize_chapter("") == ("", "")
        assert normalize_chapter("  ", "x") == ("", "x")


class TestAnalyzeParagraphStructure:
    def test_extracts_headings_roles_and_patterns(self):
        structure = analyze_paragraph_structure([SAMPLE_REF])
        headings = " ".join(structure["headings"])
        assert "3.1" in headings
        assert "3.2" in headings
        assert structure["has_tables"] is True
        assert "依据引用" in structure["rhetorical_patterns"]
        assert "结论收束" in structure["rhetorical_patterns"]
        roles = [item["role"] for item in structure["outline"]]
        assert "机构职责" in roles
        assert "目标方针" in roles
        assert "小结" in roles
        assert "写作顺序" in structure["outline_text"]

    def test_empty_reference(self):
        structure = analyze_paragraph_structure(["", "  "])
        assert structure["heading_count"] == 0
        assert structure["outline"] == []
        assert "无参考文本" in structure["outline_text"]

    def test_plain_paragraph_is_overview(self):
        structure = analyze_paragraph_structure(["本单位位于县城中心，建筑面积约1万平方米。"])
        assert structure["outline"][0]["role"] == "概述"


class TestExtractProjectFacts:
    def test_chapter3_includes_management(self):
        facts = extract_project_facts(_project(), "第3章")
        md = facts["facts_markdown"]
        assert "莘县县政府" in md
        assert "节能工作领导小组" in md
        assert "县级节能示范" in md

    def test_chapter5_includes_energy(self):
        facts = extract_project_facts(_project(), "第5章")
        md = facts["facts_markdown"]
        assert "2024年" in md
        assert "1080000" in md

    def test_chapter6_includes_equipment(self):
        facts = extract_project_facts(_project(), "第6章")
        assert "螺杆冷水机组" in facts["facts_markdown"]


class TestRetrieveReferences:
    def test_retries_without_chapter_tag_when_strict_empty(self):
        calls = []

        def fake_search(query, tags, top_k=5):
            calls.append(dict(tags))
            if "chapter" in tags:
                return {"results": [], "source": "none", "count": 0}
            return {
                "results": [{"filename": "ref.docx", "chapter": "第3章", "text": "正文"}],
                "source": "qdrant_vector",
                "count": 1,
            }

        result = retrieve_references(
            "第3章",
            {"institution_category": "党政机关"},
            context="能源资源管理状况",
            search_fn=fake_search,
        )
        assert result["count"] == 1
        assert any("chapter" in c for c in calls)
        assert any("chapter" not in c for c in calls)


class TestRunImitate:
    def test_end_to_end_with_llm(self):
        def fake_search(query, tags, top_k=5):
            return {
                "results": [{
                    "filename": "省人社厅能源审计报告.docx",
                    "chapter": "第3章",
                    "text": SAMPLE_REF,
                    "score": 0.91,
                    "tags": {"institution_category": "党政机关"},
                }],
                "source": "qdrant_tags",
                "count": 1,
            }

        def fake_llm(**kwargs):
            assert kwargs["unit_name"] == "莘县县政府"
            assert kwargs["chapter"] == "第3章"
            assert "3.1" in kwargs["outline_text"]
            assert "节能工作领导小组" in kwargs["project_facts"]
            assert "省人社厅" in kwargs["reference_excerpt"]
            return "3.1 能源资源管理机构\n\n莘县县政府成立了节能工作领导小组。"

        result = run_imitate(
            "莘县县政府",
            "3.1",
            project=_project(),
            search_fn=fake_search,
            llm_fn=fake_llm,
        )
        assert result["ok"] is True
        assert result["writer"] == "llm"
        assert result["chapter"] == "第3章"
        assert result["section"] == "3.1"
        assert "莘县县政府成立了节能工作领导小组" in result["paragraph"]
        assert result["reference_count"] == 1
        assert result["sources"][0]["filename"].startswith("省人社厅")

    def test_llm_failure_falls_back_to_draft(self):
        result = run_imitate(
            "莘县县政府",
            "第3章",
            project=_project(),
            search_fn=lambda *a, **k: {"results": [], "source": "none", "count": 0},
            llm_fn=lambda **k: None,
        )
        assert result["ok"] is True
        assert result["writer"] == "fallback"
        assert "LLM 不可用" in result["paragraph"]
        assert result["notice"]

    def test_missing_project(self, monkeypatch):
        def boom(name, refresh_from_pg=False):
            raise ProjectNotFoundError(f"未找到项目：{name}")

        monkeypatch.setattr(
            "tools.energy_audit.imitate_pipeline.load_project_data",
            boom,
        )
        result = run_imitate(
            "不存在的单位xyz",
            "第3章",
            search_fn=lambda *a, **k: {"results": [], "source": "none", "count": 0},
            llm_fn=lambda **k: "不应调用",
        )
        assert result["ok"] is False
        assert result["paragraph"] == ""
        assert "未找到" in result["error"]

    def test_empty_chapter(self):
        result = run_imitate("莘县县政府", "", project=_project())
        assert result["ok"] is False
        assert "chapter" in result["error"]


class TestLoadProjectData:
    def test_uses_local_project_when_present(self, monkeypatch):
        local = _project()
        monkeypatch.setattr(
            "tools.energy_audit.imitate_pipeline.load_project",
            lambda name: local,
        )
        loaded = load_project_data("莘县县政府")
        assert loaded.base.unit_name == "莘县县政府"

    def test_refresh_calls_pg(self, monkeypatch):
        called = {}

        def fake_build(name):
            called["name"] = name
            return _project()

        monkeypatch.setattr(
            "tools.energy_audit.pg_collector.build_and_save_project",
            fake_build,
        )
        loaded = load_project_data("莘县县政府", refresh_from_pg=True)
        assert called["name"] == "莘县县政府"
        assert loaded.base.unit_name == "莘县县政府"

    def test_missing_raises(self, monkeypatch):
        monkeypatch.setattr(
            "tools.energy_audit.imitate_pipeline.load_project",
            lambda name: None,
        )

        def fake_build(name):
            return AuditProject(base=ProjectBase(name="", unit_name=""))

        monkeypatch.setattr(
            "tools.energy_audit.pg_collector.build_and_save_project",
            fake_build,
        )
        with pytest.raises(ProjectNotFoundError):
            load_project_data("幽灵单位")


class TestLlmImitatePrompt:
    def test_prompt_contains_structure_and_facts(self, monkeypatch):
        captured = {}

        def fake_chat(messages, **kwargs):
            captured["messages"] = messages
            captured["kwargs"] = kwargs
            return "仿写结果"

        monkeypatch.setattr("tools.energy_audit.llm_client._chat", fake_chat)
        from tools.energy_audit.llm_client import imitate_from_structure

        text = imitate_from_structure(
            unit_name="莘县县政府",
            chapter="第3章",
            section="3.1",
            outline_text="写作顺序：1. 机构职责",
            project_facts="管理机构：节能领导小组",
            reference_excerpt="省人社厅成立了领导小组",
        )
        assert text == "仿写结果"
        system = captured["messages"][0]["content"]
        user = captured["messages"][1]["content"]
        assert "禁止照抄" in system
        assert "写作顺序" in user
        assert "节能领导小组" in user
        assert captured["kwargs"]["task"] == "energy_audit_imitate"
    def test_handler_requires_project_and_chapter(self):
        err = json.loads(_handle_imitate_paragraph({"chapter": "第3章"}))
        assert "project_name" in err["error"]
        err = json.loads(_handle_imitate_paragraph({"project_name": "某单位"}))
        assert "chapter" in err["error"]

    def test_handler_returns_paragraph(self, monkeypatch):
        monkeypatch.setattr(
            "tools.energy_audit.imitate_pipeline.run_imitate",
            lambda *a, **k: {
                "ok": True,
                "paragraph": "仿写正文",
                "writer": "llm",
                "chapter": "第3章",
                "section": "",
                "tags": {},
                "structure": {"outline": []},
                "sources": [],
                "reference_source": "none",
                "reference_count": 0,
                "project": {"unit_name": "某单位"},
                "notice": None,
            },
        )
        payload = json.loads(_handle_imitate_paragraph({
            "project_name": "某单位",
            "chapter": "第3章",
        }))
        assert payload["ok"] is True
        assert payload["paragraph"] == "仿写正文"

    def test_rest_error_envelope(self):
        out = rest_imitate_energy_audit_paragraph("", "第3章")
        assert "error" in out
        out = rest_imitate_energy_audit_paragraph("某单位", "")
        assert "error" in out
