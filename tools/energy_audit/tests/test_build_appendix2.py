import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = (
    REPO_ROOT
    / "skills"
    / "energy-audit"
    / "energy-audit-report"
    / "scripts"
    / "build_appendix2.py"
)


def load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_appendix2_under_test",
        SCRIPT_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_year_table_caption_uses_local_table_number():
    builder = load_builder()
    year = {
        "year": 2024,
        "monthly_water_m3": [1] * 12,
        "monthly_water_cost": [1] * 12,
        "water_m3": 12,
        "water_cost_wan": 0.0012,
        "monthly_electricity_kwh": [1] * 12,
        "monthly_electricity_cost": [1] * 12,
        "electricity_kwh": 12,
        "electricity_cost_wan": 0.0012,
    }

    text, _ = builder.build_year_table(year, 1, [])

    assert text.splitlines()[0] == "表1 2024年逐月能源资源消耗及费用统计表"


def test_summary_caption_is_renumbered_after_yearly_tables():
    builder = load_builder()
    old = (
        "附表2-4 三年能源资源消耗汇总表\n\n"
        "| 年份 | 电量 |\n"
        "| --- | --- |\n"
        "| 2024 | 100 |\n"
    )

    assert builder.keep_summary(old, 4).startswith("表4 三年能源资源消耗汇总表")
