import importlib.util
import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

from docx import Document
from docx.oxml.ns import qn


ROOT = Path(__file__).resolve().parents[5]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


BUILD_MOD = load_module(
    "public_building_table_builder_under_test",
    Path(__file__).resolve().parents[3]
    / "energy-audit-report"
    / "scripts"
    / "build_energy_audit_docx.py",
)
DOCX_ASSERTS = load_module(
    "public_building_table_asserts_under_test",
    Path(__file__).resolve().parents[3]
    / "energy-audit-report"
    / "scripts"
    / "ea_docx_asserts.py",
)

PUBLIC_BUILDING = SimpleNamespace(is_public_building=True)
PUBLIC_INSTITUTION = SimpleNamespace(is_public_building=False)


def fixed_rows():
    return [
        ["建筑物名称", "专家公寓", "建筑面积（m²）", "19418.41"],
        ["建筑地址", "—", "投用年份", "2022"],
        ["建筑层数", "地上19层", "建筑高度（m）", "66.95"],
        [
            "建筑结构形式",
            "钢筋混凝土框架核心筒",
            "建筑透明围护结构",
            "中空双层玻璃窗",
        ],
        ["夏季空调冷源", "空气源热泵", "冬季供暖热源", "空气源热泵"],
        ["夏季空调末端形式", "风机盘管", "冬季供暖末端形式", "风机盘管"],
        [
            "建筑外墙保温",
            "外墙保温",
            "生活热水系统",
            "空气源热泵热水系统",
        ],
        ["建筑给水系统", "市政供水", "能耗在线监测系统", "有"],
    ]


def public_institution_rows():
    return [
        ["建筑物名称", "某楼", "建筑地址", "某路1号"],
        ["建造年代", "2010年", "建筑功能", "科研办公"],
        ["建筑层数及朝向", "地上8层", "建筑面积", "12000 m²"],
        ["建筑功能分区", "办公、会议", "建筑结构形式", "框架"],
        ["建筑外窗类型", "中空玻璃", "建筑外墙保温", "有"],
        ["夏季空调冷源", "冷水机组", "冬季供暖热源", "市政热力"],
        ["夏季空调末端形式", "风机盘管", "冬季供暖末端形式", "散热器"],
        ["建筑给水系统", "市政供水", "建筑消防给水系统", "市政供水"],
        ["生活热水系统", "电热水器", "能耗在线监测系统", "有"],
    ]


def markdown_for(rows, *, caption="表2.1 专家公寓建筑信息统计", include_caption=True):
    lines = [
        "# 第2章 建筑概况",
        "",
        "## 2.2 建筑物概况",
        "",
    ]
    if include_caption:
        lines += [caption, ""]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines) + "\n"


def render_markdown(tmp: Path, text: str, family_context):
    md_path = tmp / "ch2.md"
    md_path.write_text(text, encoding="utf-8")
    doc = Document()
    BUILD_MOD._setup_bullet_numbering(doc)
    BUILD_MOD._render_md(
        doc,
        str(md_path),
        {
            "project_dir": str(tmp),
            "family_context": family_context,
        },
    )
    return doc


def document_xml(doc) -> str:
    buffer = io.BytesIO()
    doc.save(buffer)
    with zipfile.ZipFile(buffer) as zf:
        return zf.read("word/document.xml").decode("utf-8")


def numbering_xml(doc) -> str:
    buffer = io.BytesIO()
    doc.save(buffer)
    with zipfile.ZipFile(buffer) as zf:
        return zf.read("word/numbering.xml").decode("utf-8")


class PublicBuildingListAssemblyTests(unittest.TestCase):
    def test_markdown_basis_list_uses_solid_wingdings_bullets(self):
        text = (
            "# 第1章 能源审计执行概要\n\n"
            "## 1.6 审计依据\n\n"
            "- 《公共建筑节能改造技术规范》（JGJ 176-2009）；\n"
            "- 调研资料及其他相关资料。\n"
        )

        with tempfile.TemporaryDirectory() as tmp:
            doc = render_markdown(Path(tmp), text, PUBLIC_BUILDING)

        bullets = [
            p
            for p in doc.paragraphs
            if p.text in {
                "《公共建筑节能改造技术规范》（JGJ 176-2009）；",
                "调研资料及其他相关资料。",
            }
        ]
        self.assertEqual(len(bullets), 2)
        for paragraph in bullets:
            num_pr = paragraph._p.pPr.find(qn("w:numPr"))
            self.assertIsNotNone(num_pr)
            self.assertEqual(
                num_pr.find(qn("w:numId")).get(qn("w:val")),
                "1",
            )
            self.assertFalse(paragraph.text.startswith("- "))
            self.assertNotIn("- ", paragraph.text)

        numbering = numbering_xml(doc)
        self.assertIn('<w:numFmt w:val="bullet"', numbering)
        self.assertIn(f'<w:lvlText w:val="{BUILD_MOD.BULLET_CHAR}"', numbering)
        self.assertIn('<w:rFonts w:ascii="Wingdings"', numbering)
        self.assertNotIn("- 《公共建筑节能改造技术规范》", document_xml(doc))


class PublicBuildingTableAssemblyTests(unittest.TestCase):
    def test_public_building_table_is_four_columns_and_eight_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = render_markdown(
                Path(tmp),
                markdown_for(fixed_rows()),
                PUBLIC_BUILDING,
            )

        table = doc.tables[0]
        self.assertEqual(len(table.columns), 4)
        self.assertEqual(len(table.rows), 8)
        self.assertEqual(table.rows[0].cells[0].text, "建筑物名称")
        self.assertFalse(
            any(
                run.bold
                for row in table.rows
                for cell in row.cells
                for paragraph in cell.paragraphs
                for run in paragraph.runs
            )
        )
        self.assertNotIn("<w:tblHeader", table._tbl.xml)
        for row in table.rows:
            self.assertIsNotNone(row._tr.trPr.find(qn("w:cantSplit")))
            self.assertAlmostEqual(row.height.cm, 1.01, places=2)

    def test_public_building_rejects_wrong_table_contract(self):
        legacy_ten_columns = [
            [
                "建筑名称",
                "专家公寓",
                "建筑面积（m²）",
                "19418.41",
                "建筑层数",
                "地上19层",
                "建筑高度（m）",
                "66.95",
                "投用年份",
                "2022",
            ]
        ]
        swapped_rows = fixed_rows()
        swapped_rows[1][0], swapped_rows[2][0] = (
            swapped_rows[2][0],
            swapped_rows[1][0],
        )

        for rows in (legacy_ten_columns, public_institution_rows(), swapped_rows):
            with self.subTest(rows=rows):
                with tempfile.TemporaryDirectory() as tmp:
                    with self.assertRaisesRegex(
                        ValueError, "公共建筑建筑信息统计表"
                    ):
                        render_markdown(
                            Path(tmp),
                            markdown_for(rows),
                            PUBLIC_BUILDING,
                        )

    def test_public_institution_table_keeps_existing_assembly_behavior(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = render_markdown(
                Path(tmp),
                markdown_for(
                    public_institution_rows(),
                    caption="表2.1 某楼基本信息",
                ),
                PUBLIC_INSTITUTION,
            )

        table = doc.tables[0]
        self.assertEqual(len(table.columns), 4)
        self.assertEqual(len(table.rows), 9)
        self.assertIn("<w:tblHeader", table._tbl.xml)

    def test_public_institution_building_alias_keeps_existing_behavior(self):
        rows = public_institution_rows()
        rows[0][0] = "建筑名称"
        with tempfile.TemporaryDirectory() as tmp:
            doc = render_markdown(
                Path(tmp),
                markdown_for(
                    rows,
                    caption="表2.1 某楼基本信息",
                ),
                PUBLIC_INSTITUTION,
            )

        table = doc.tables[0]
        self.assertIn("<w:tblHeader", table._tbl.xml)
        self.assertTrue(
            any(
                run.bold
                for cell in table.rows[0].cells
                for paragraph in cell.paragraphs
                for run in paragraph.runs
            )
        )


class PublicBuildingTableAssertionTests(unittest.TestCase):
    def test_docx_checks_accept_exact_fixed_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = render_markdown(
                Path(tmp),
                markdown_for(fixed_rows()),
                PUBLIC_BUILDING,
            )

        checks, details = DOCX_ASSERTS.public_building_table_checks(
            document_xml(doc)
        )

        self.assertTrue(checks["pb_bldg_table"], details)
        self.assertTrue(checks["pb_bldg_table_title"], details)
        self.assertTrue(checks["pb_bldg_table_no_repeat_header"], details)

    def test_docx_checks_reject_wrong_table_and_nonadjacent_caption(self):
        with tempfile.TemporaryDirectory() as tmp:
            wrong_doc = render_markdown(
                Path(tmp),
                markdown_for(public_institution_rows()),
                PUBLIC_INSTITUTION,
            )
        with tempfile.TemporaryDirectory() as tmp:
            uncaptioned_doc = render_markdown(
                Path(tmp),
                markdown_for(fixed_rows(), include_caption=False),
                PUBLIC_BUILDING,
            )

        wrong_checks, _ = DOCX_ASSERTS.public_building_table_checks(
            document_xml(wrong_doc)
        )
        caption_checks, caption_details = (
            DOCX_ASSERTS.public_building_table_checks(
                document_xml(uncaptioned_doc)
            )
        )

        self.assertFalse(wrong_checks["pb_bldg_table"])
        self.assertFalse(caption_checks["pb_bldg_table_title"])
        self.assertIn("表题", caption_details["pb_bldg_table_title"])


if __name__ == "__main__":
    unittest.main()
