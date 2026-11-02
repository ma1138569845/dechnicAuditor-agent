import importlib.util
from pathlib import Path
import re

from docx import Document


REPO_ROOT = Path(__file__).resolve().parents[3]
BUILDER_PATH = (
    REPO_ROOT
    / "skills"
    / "energy-audit"
    / "energy-audit-report"
    / "scripts"
    / "build_energy_audit_docx.py"
)
ASSERTS_PATH = (
    REPO_ROOT
    / "skills"
    / "energy-audit"
    / "energy-audit-report"
    / "scripts"
    / "ea_docx_asserts.py"
)


def load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_energy_audit_docx_under_test", BUILDER_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_asserts():
    spec = importlib.util.spec_from_file_location(
        "ea_docx_asserts_under_test", ASSERTS_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hotel_comparable_formula_renders_as_word_math_not_flat_text():
    builder = load_builder()
    omml = builder._load_omml()
    assert "FORMULA10" in omml

    doc = Document()
    builder._render_formula_line(doc, "[FORMULA10]", omml)
    xml = doc._element.xml

    assert xml.count("<m:oMath") == 1
    assert "<m:t>kd</m:t>" in xml
    assert "<m:t>j</m:t>" in xml
    assert "<m:t>1</m:t>" in xml
    assert "<m:t>m</m:t>" in xml
    assert "Ekd=Ej" not in "".join(doc.paragraphs[0].text.split())


def test_bed_year_water_formula_uses_bed_count_times_occupancy():
    builder = load_builder()
    formula = builder._load_omml()["FORMULA9"]
    formula_text = "".join(
        re.findall(r"<m:t(?: [^>]*)?>([^<]*)</m:t>", formula)
    )

    assert formula_text == "Vuc=VkN×Q"


def test_public_building_check_accepts_bed_year_water_formula_with_occupancy():
    module = load_asserts()
    builder = load_builder()
    text = """
    5.3.2 单位床年用水量
    单位床年用水量按下式计算：
    Vuc——单位床年用水量，单位为立方米每床年（m³/(床·年)）；
    Vk——年度用水量，单位为立方米每年（m³/a）；
    N——总床位数，单位为床；
    Q——宾馆床位出租率。
    本项目按 H6110 旅游饭店—三星级（或具有同等规模、质量、水平）
    匹配用水定额，定额单位为 m³/(床·年)。
    定额标准通用值（m³/(床·年)） 256
    定额标准先进值（m³/(床·年)） 146
    评价结果 低于先进值
    """
    doc_xml = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/'
        'wordprocessingml/2006/main">'
        + builder._load_omml()["FORMULA9"]
        + "</w:document>"
    )

    checks, details = module.public_building_checks(text, doc_xml)

    assert checks["pb_ch5_bed_year_water_formula"] is True
    assert "pb_ch5_bed_year_water_formula" not in details


def test_public_building_check_rejects_old_bed_only_water_formula():
    module = load_asserts()
    text = """
    5.3.2 单位床年用水量
    单位床年用水量按下式计算：
    Vuc——单位床年用水量，单位为立方米每床年（m³/(床·年)）；
    Vk——年度用水量，单位为立方米每年（m³/a）；
    N——总床位数，单位为床；
    Q——宾馆床位出租率。
    """
    doc_xml = (
        '<w:document xmlns:m="http://schemas.openxmlformats.org/'
        'officeDocument/2006/math">'
        '<m:oMath><m:r><m:t>Vuc=Vk/N</m:t></m:r></m:oMath>'
        "</w:document>"
    )

    checks, details = module.public_building_checks(text, doc_xml)

    assert checks["pb_ch5_bed_year_water_formula"] is False
    assert "N×Q" in details["pb_ch5_bed_year_water_formula"]


def test_public_building_check_accepts_standard_760_formula_symbols():
    module = load_asserts()
    builder = load_builder()
    text = """
    5.3.1 单位可比综合能耗
    式中：
    Ekd——单位可比综合能耗，单位为千克标准煤每平方米（kgce/m²）；
    Ej——单位综合能耗，单位为千克标准煤每平方米（kgce/m²）；
    a——综合能耗修正系数；
    m——第m项综合能耗修正系数。
    """
    doc_xml = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/'
        'wordprocessingml/2006/main">'
        + builder._load_omml()["FORMULA10"]
        + "</w:document>"
    )

    checks, details = module.public_building_checks(text, doc_xml)

    assert checks["pb_ch5_760_formula"] is True
    assert "pb_ch5_760_formula" not in details


def test_vertical_public_building_appendix2_accepts_page_break_without_duplicate(
):
    module = load_asserts()
    doc_xml = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/'
        'wordprocessingml/2006/main">'
        '<w:p><w:pPr><w:pStyle w:val="Heading2"/>'
        '<w:pageBreakBefore/></w:pPr><w:r><w:t>'
        '附录2：各种能源折标准煤参考系数'
        '</w:t></w:r></w:p>'
        '</w:document>'
    )

    ok, reason = module._chapter_pagebreak_ok(
        doc_xml, apx2_sectioned=False
    )

    assert ok, reason


def test_public_building_check_requires_native_760_formula_object():
    module = load_asserts()
    text = """
    5.3.1 单位可比综合能耗
    式中：
    Ekd——单位可比综合能耗，单位为千克标准煤每平方米（kgce/m²）；
    Ej——单位综合能耗，单位为千克标准煤每平方米（kgce/m²）；
    a——综合能耗修正系数；
    m——第m项综合能耗修正系数。
    """

    checks, details = module.public_building_checks(
        text,
        '<w:document xmlns:w="http://schemas.openxmlformats.org/'
        'wordprocessingml/2006/main"></w:document>',
    )

    assert checks["pb_ch5_760_formula"] is False
    assert "OMML" in details["pb_ch5_760_formula"]


def test_public_building_check_rejects_nonstandard_product_description():
    module = load_asserts()
    text = """
    5.3.1 单位可比综合能耗
    式中：
    Ekd——单位可比综合能耗，单位为千克标准煤每平方米（kgce/m²）；
    Ej——单位综合能耗，单位为千克标准煤每平方米（kgce/m²）；
    a1×a2×…×am——各项修正系数连乘值。
    """

    checks, details = module.public_building_checks(text)

    assert checks["pb_ch5_760_formula"] is False
    assert "综合能耗修正系数" in details["pb_ch5_760_formula"]


def test_public_building_check_requires_unified_760_tier_labels():
    module = load_asserts()
    text = """
    5.3.1 单位可比综合能耗
    定额标准约束值（kgce/m²） 25
    定额标准基准值（kgce/m²） 18
    定额标准引导值（kgce/m²） 12
    评价结果 低于引导值
    """

    checks, details = module.public_building_checks(text)

    assert checks["pb_ch5_760_tiers"] is True
    assert "pb_ch5_760_tiers" not in details


def test_public_building_check_rejects_legacy_760_tier_labels():
    module = load_asserts()
    text = """
    5.3.1 单位可比综合能耗
    定额标准3级（限额值）（kgce/m²） 25
    定额标准2级（约束值）（kgce/m²） 18
    定额标准1级（先进值）（kgce/m²） 12
    评价结果 低于1级（先进值）
    """

    checks, details = module.public_building_checks(text)

    assert checks["pb_ch5_760_tiers"] is False
    assert "约束值、基准值、引导值" in details["pb_ch5_760_tiers"]


def test_public_building_check_accepts_h6110_three_star_water_quota():
    module = load_asserts()
    text = """
    5.3.2 单位床年用水量
    本项目按 H6110 旅游饭店—三星级（或具有同等规模、质量、水平）
    匹配用水定额，定额单位为 m³/(床·年)。
    定额标准通用值（m³/(床·年)） 256
    定额标准先进值（m³/(床·年)） 146
    评价结果 低于先进值
    """

    checks, details = module.public_building_checks(text)

    assert checks["pb_ch5_water_quota"] is True
    assert "pb_ch5_water_quota" not in details


def test_public_building_check_accepts_explicit_h6120_general_hotel_quota():
    module = load_asserts()
    text = """
    5.3.2 单位床年用水量
    本项目按 H6120 一般旅馆—星级以下（招待所、旅社）匹配用水定额。
    定额标准通用值（m³/(床·年)） 125
    定额标准先进值（m³/(床·年)） 70
    评价结果 低于先进值
    """

    checks, details = module.public_building_checks(text)

    assert checks["pb_ch5_water_quota"] is True
    assert "pb_ch5_water_quota" not in details


def test_public_building_check_rejects_h6120_for_platform_starred_hotel():
    module = load_asserts()
    text = """
    5.3.2 单位床年用水量
    本项目按 H6110 旅游饭店—三星级（或具有同等规模、质量、水平）
    匹配用水定额，但仍按一般旅馆口径评价。
    定额标准通用值（m³/(床·年)） 125
    定额标准先进值（m³/(床·年)） 70
    """

    checks, details = module.public_building_checks(text)

    assert checks["pb_ch5_water_quota"] is False
    assert "H6110" in details["pb_ch5_water_quota"]
