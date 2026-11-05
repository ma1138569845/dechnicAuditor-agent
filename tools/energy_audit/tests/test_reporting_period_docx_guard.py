import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
BUILDER_PATH = (
    REPO_ROOT
    / "skills"
    / "energy-audit"
    / "energy-audit-report"
    / "scripts"
    / "build_energy_audit_docx.py"
)


def load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_energy_audit_docx_reporting_guard", BUILDER_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_chapters(
    project_dir: Path,
    chapter5: str = "",
    appendix: str = "",
) -> None:
    md_dir = project_dir / "chapter_md"
    md_dir.mkdir()
    (md_dir / "ch5_import.md").write_text(chapter5, encoding="utf-8")
    (md_dir / "appendix.md").write_text(appendix, encoding="utf-8")


def incomplete_project() -> dict:
    return {
        "buildings": [{"begin_date": "2022-08"}],
        "energy_yearly": [
            {
                "year": 2022,
                "electricity_kwh": 100,
                "monthly_electricity_kwh": [
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    20,
                    20,
                    20,
                    20,
                    20,
                ],
            },
            {
                "year": 2023,
                "electricity_kwh": 100,
                "monthly_electricity_kwh": [100 / 12] * 12,
            },
        ],
    }


def test_guard_rejects_incomplete_year_in_any_table_or_monthly_appendix(
    tmp_path,
):
    builder = load_builder()
    write_chapters(
        tmp_path,
        chapter5=(
            "正文可说明2022年仅有8—12月数据。\n\n"
            "| 项目 | 2022年 | 2023年 |\n"
            "| --- | --- | --- |\n"
            "| 单位综合能耗 | 1 | 2 |\n"
        ),
        appendix=(
            "表1 2022年逐月能源资源消耗及费用统计表\n\n"
            "| 月份 | 电量 |\n"
            "| --- | --- |\n"
            "| 8月 | 20 |\n"
        ),
    )

    with pytest.raises(builder.ReportFamilyContractError, match="2022年"):
        builder.validate_reporting_period_tables(
            str(tmp_path), incomplete_project()
        )


def test_guard_allows_narrative_explanation_without_incomplete_year_tables(
    tmp_path,
):
    builder = load_builder()
    write_chapters(
        tmp_path,
        chapter5=(
            "正文说明2022年仅有8—12月数据，属于不完整年度。\n\n"
            "| 项目 | 2023年 |\n"
            "| --- | --- |\n"
            "| 单位综合能耗 | 2 |\n"
        ),
        appendix=(
            "表1 2023年逐月能源资源消耗及费用统计表\n\n"
            "| 月份 | 电量 |\n"
            "| --- | --- |\n"
            "| 1月 | 100 |\n"
        ),
    )

    assert (
        builder.validate_reporting_period_tables(
            str(tmp_path), incomplete_project()
        )
        is None
    )


def test_guard_ignores_non_report_context_markdown(tmp_path):
    builder = load_builder()
    write_chapters(
        tmp_path,
        chapter5=(
            "正文说明2022年仅有8—12月数据，属于不完整年度。\n\n"
            "| 项目 | 2023年 |\n"
            "| --- | --- |\n"
            "| 单位综合能耗 | 2 |\n"
        ),
        appendix="表1 各种能源折标准煤参考系数\n",
    )
    (tmp_path / "chapter_md" / "_context.md").write_text(
        "| 年份 | 电量 |\n"
        "| --- | --- |\n"
        "| 2022年 | 100 |\n",
        encoding="utf-8",
    )

    assert (
        builder.validate_reporting_period_tables(
            str(tmp_path), incomplete_project()
        )
        is None
    )


def test_new_appendix_table_captions_render_as_appendix_captions(tmp_path):
    builder = load_builder()
    appendix = (
        "# 附录：\n\n"
        "## 附录1：建筑基本信息及设备统计表\n\n"
        "附表1-1 建筑基本信息表\n\n"
        "| 项目 | 内容 |\n"
        "| --- | --- |\n"
        "| 建筑物名称 | 测试楼 |\n\n"
        "## 附录2：建筑能耗数据信息表\n\n"
        "表1 2024年逐月能源资源消耗及费用统计表\n\n"
        "| 月份 | 电量 |\n"
        "| --- | --- |\n"
        "| 1月 | 100 |\n"
    )
    appendix_path = tmp_path / "appendix.md"
    appendix_path.write_text(appendix, encoding="utf-8")

    document = builder.Document()
    builder._setup_styles(document)
    builder._render_md(
        document,
        str(appendix_path),
        {
            "project_dir": str(tmp_path),
            "omml": {},
            "images": {},
            "figure_issues": {},
            "family_context": SimpleNamespace(is_public_building=False),
        },
        appendix=True,
    )

    captions = [
        paragraph
        for paragraph in document.paragraphs
        if paragraph.text.startswith("表1 ")
    ]
    assert len(captions) == 2
    assert all(
        paragraph.alignment == builder.WD_ALIGN_PARAGRAPH.CENTER
        for paragraph in captions
    )
    assert all(paragraph.runs[0].bold for paragraph in captions)
