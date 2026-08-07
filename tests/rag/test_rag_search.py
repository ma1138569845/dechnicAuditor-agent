"""Tests for rag.rag_search fallback chain (vector -> wiki -> knowledge graph)."""

import pytest

from rag import rag_search as rs


@pytest.fixture(autouse=True)
def _clear_kg_cache():
    """Reset the lazy knowledge-graph singleton between tests."""
    old = rs._kg_instance
    rs._kg_instance = None
    yield
    rs._kg_instance = old


def test_infer_system_from_query():
    assert rs._infer_system("冷机COP偏低", {}) == "中央空调系统"
    assert rs._infer_system("锅炉效率下降", {}) == "供暖系统"
    assert rs._infer_system("LED照明改造", {}) == "照明系统"
    assert rs._infer_system("单位建筑面积能耗", {}) is None


def test_search_knowledge_graph_direct_diagnosis():
    results = rs.search_knowledge_graph("冷机COP偏低")
    assert len(results) == 1
    assert results[0]["filename"] == "knowledge_graph"
    assert "COP" in results[0]["chapter"]
    assert results[0]["score"] > 0
    assert "最可能原因" in results[0]["text"]


def test_search_knowledge_graph_system_measures_fallback(monkeypatch):
    # A generic system query without a matching anomaly should fall back to measures.
    class FakeKG:
        def diagnose(self, *args, **kwargs):
            class EmptyResult:
                has_diagnosis = False
            return EmptyResult()

        def get_measures_for_system(self, system):
            return [{
                "label": "降低冷冻水泵频率",
                "description": "通过变频器降低水泵频率",
                "saving_rate": "15-30%",
                "investment": "零投资",
                "payback": "即时",
            }]

    monkeypatch.setattr(rs, "_get_knowledge_graph", FakeKG)

    results = rs.search_knowledge_graph("中央空调系统节能措施")
    assert len(results) == 1
    assert results[0]["filename"] == "knowledge_graph"
    assert results[0]["tags"]["system"] == "中央空调系统"
    assert "节能措施推荐" in results[0]["text"]
    assert "降低冷冻水泵频率" in results[0]["text"]


def test_search_knowledge_graph_empty_for_unrelated_query():
    results = rs.search_knowledge_graph("abcdefghxyz12345 无关查询")
    assert results == []


def test_search_reports_knowledge_graph_fallback(monkeypatch):
    """When Qdrant and wiki return nothing, search_reports falls back to the knowledge graph."""
    monkeypatch.setattr(rs, "search_by_tags", lambda *a, **kw: [])
    monkeypatch.setattr(rs, "search_qdrant", lambda *a, **kw: [])
    monkeypatch.setattr(rs, "search_wiki", lambda *a, **kw: [])

    result = rs.search_reports("冷机COP偏低", tags={"institution_category": "医疗"})

    assert result["source"] == "knowledge_graph"
    assert result["count"] == 1
    assert result["results"][0]["filename"] == "knowledge_graph"
    assert "COP" in result["results"][0]["chapter"]


def test_search_reports_respects_existing_source(monkeypatch):
    """If wiki returns results, knowledge graph is not consulted."""
    wiki_hit = [{"score": 0.8, "filename": "x.md", "chapter": "c", "text": "t", "tags": {}}]
    monkeypatch.setattr(rs, "search_by_tags", lambda *a, **kw: [])
    monkeypatch.setattr(rs, "search_qdrant", lambda *a, **kw: [])
    monkeypatch.setattr(rs, "search_wiki", lambda *a, **kw: wiki_hit)

    result = rs.search_reports("冷机COP偏低")
    assert result["source"] == "wiki"
    assert result["count"] == 1
    assert result["results"] == wiki_hit
