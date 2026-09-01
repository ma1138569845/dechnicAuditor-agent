"""本地同类参考报告库：按审计类型 / 机构类别打分并切章。"""

from pathlib import Path

from tools.energy_audit.reference_library import (
    chunk_report_text,
    infer_audit_type,
    list_reference_files,
    resolve_reference_dir,
    score_reference,
    search_local_references,
)


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


SAMPLE_CH3 = """第3章 能源资源管理状况

3.1 能源资源管理机构职责

根据《公共机构节能条例》，山东省人力资源和社会保障厅成立了节能工作领导小组。

3.2 能源资源管理目标和方针

该单位将年度节能目标分解到责任处室。
"""

SAMPLE_CH2 = """第2章 公共机构概况

2.1 公共机构基本情况

某市中心医院开放床位800张，承担区域医疗服务。
"""


class TestResolveAndList:
    def test_explicit_dir_wins(self, tmp_path, monkeypatch):
        monkeypatch.delenv("EA_REFERENCE_DIR", raising=False)
        target = tmp_path / "refs"
        target.mkdir()
        assert resolve_reference_dir(str(target)) == target.resolve()

    def test_default_is_hermes_rag_report(self, monkeypatch):
        monkeypatch.delenv("EA_REFERENCE_DIR", raising=False)
        from hermes_constants import get_hermes_home

        expected = (get_hermes_home() / "rag" / "report").resolve()
        assert resolve_reference_dir() == expected
        assert resolve_reference_dir("") == expected

    def test_lists_type_subdirs(self, tmp_path):
        _write(tmp_path, "公共机构/法院报告.md", SAMPLE_CH3)
        _write(tmp_path, "工业企业/钢厂报告.md", "第1章 概要\n正文")
        files = list_reference_files(tmp_path)
        names = {p.name for p in files}
        assert names == {"法院报告.md", "钢厂报告.md"}


class TestScoring:
    def test_same_type_and_court_outrank_hospital(self, tmp_path):
        court = _write(tmp_path, "公共机构/烟台经济技术开发区人民法院能源审计报告.md", SAMPLE_CH3)
        hospital = _write(tmp_path, "公共机构/某市中心医院能源审计报告.md", SAMPLE_CH2)
        industrial = _write(tmp_path, "工业企业/某钢厂能源审计报告.md", "第1章")
        tags = {"audit_type": "公共机构", "institution_category": "党政机关", "specific_type": "法院"}
        assert score_reference(court, tags) > score_reference(hospital, tags)
        assert score_reference(industrial, tags) < 0

    def test_infer_type_from_folder(self, tmp_path):
        path = _write(tmp_path, "公共建筑/某写字楼.md", "第1章")
        assert infer_audit_type(path, path.name) == "公共建筑"


class TestChunkAndSearch:
    def test_chunk_splits_chapters(self):
        text = "封面文字\n第1章 概要\n目的说明\n第2章 概况\n单位介绍"
        chunks = chunk_report_text(text, filename="a.md")
        labels = [c["chapter"][:3] for c in chunks]
        assert "第1章" in labels[1] or any("第1章" in c["chapter"] for c in chunks)
        ch2 = [c for c in chunks if "第2章" in c["chapter"]]
        assert ch2 and "单位介绍" in ch2[0]["text"]

    def test_search_returns_matching_chapter_from_same_type(self, tmp_path):
        _write(tmp_path, "公共机构/烟台经济技术开发区人民法院能源审计报告.md", SAMPLE_CH3)
        _write(tmp_path, "公共机构/某市中心医院能源审计报告.md", SAMPLE_CH2)
        _write(tmp_path, "工业企业/某钢厂能源审计报告.md", "第3章 能源管理\n工厂工艺能耗管理")
        result = search_local_references(
            "第3章",
            tags={"audit_type": "公共机构", "institution_category": "党政机关", "specific_type": "法院"},
            top_k=3,
            root=tmp_path,
        )
        assert result["source"] == "local_folder"
        assert result["count"] >= 1
        top = result["results"][0]
        assert "人民法院" in top["filename"]
        assert "节能工作领导小组" in top["text"]
        assert top["tags"]["audit_type"] == "公共机构"
        assert all(r["tags"]["audit_type"] == "公共机构" for r in result["results"])

    def test_empty_folder(self, tmp_path):
        result = search_local_references("第3章", tags={"audit_type": "公共机构"}, root=tmp_path)
        assert result["results"] == []
        assert result["count"] == 0


class TestGeoFirstSearch:
    def test_infer_places_from_unit_and_address(self):
        from tools.energy_audit.reference_library import infer_places_from_text

        yantai = infer_places_from_text("烟台经济技术开发区人民法院")
        assert yantai["district"] == "烟台经济技术开发区"
        shenxian = infer_places_from_text("山东省聊城市莘县")
        assert shenxian["city"] == "聊城"
        assert shenxian["district"] == "莘县"

    def test_district_folder_beats_other_city(self, tmp_path):
        local = _write(
            tmp_path,
            "山东/烟台/经济技术开发区/公共机构/烟台经开区法院.md",
            SAMPLE_CH3,
        )
        other = _write(
            tmp_path,
            "山东/青岛/经济技术开发区/公共机构/青岛经开区法院.md",
            "第3章 能源资源管理状况\n青岛经济技术开发区某法院节能领导小组。",
        )
        tags = {
            "audit_type": "公共机构",
            "province": "山东",
            "city": "烟台",
            "district": "经济技术开发区",
            "institution_category": "党政机关",
            "specific_type": "法院",
        }
        assert score_reference(local, tags) > score_reference(other, tags)
        result = search_local_references("第3章", tags=tags, top_k=3, root=tmp_path)
        assert result["geo_scope"] == "district"
        assert result["results"][0]["filename"] == "烟台经开区法院.md"
        assert all("青岛" not in r["filename"] for r in result["results"])

    def test_widens_district_to_city_then_province(self, tmp_path):
        _write(tmp_path, "山东/青岛/市南/公共机构/青岛市南医院.md", SAMPLE_CH2)
        city_hit = _write(
            tmp_path,
            "山东/烟台/芝罘/公共机构/烟台芝罘机关.md",
            SAMPLE_CH3,
        )
        tags = {
            "audit_type": "公共机构",
            "province": "山东",
            "city": "烟台",
            "district": "福山",
        }
        result = search_local_references("第3章", tags=tags, top_k=3, root=tmp_path)
        assert result["geo_scope"] == "city"
        assert result["results"][0]["path"] == str(city_hit)

        province_only = {
            "audit_type": "公共机构",
            "province": "山东",
            "city": "济南",
            "district": "历下",
        }
        widened = search_local_references("第3章", tags=province_only, top_k=5, root=tmp_path)
        assert widened["geo_scope"] == "province"
        assert widened["count"] >= 1

    def test_filename_place_matches_without_folder_layout(self, tmp_path):
        _write(tmp_path, "烟台经济技术开发区人民法院能源审计报告.md", SAMPLE_CH3)
        _write(tmp_path, "济南市中心医院能源审计报告.md", SAMPLE_CH2)
        result = search_local_references(
            "第3章",
            tags={
                "audit_type": "公共机构",
                "province": "山东",
                "city": "烟台",
                "district": "烟台经济技术开发区",
            },
            top_k=3,
            root=tmp_path,
        )
        assert result["geo_scope"] == "district"
        assert "烟台经济技术开发区人民法院" in result["results"][0]["filename"]
