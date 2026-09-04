"""
能源审计报告生成工具
生成符合《能源审计报告编写格式规范标准》的 Word + Markdown 报告

格式规范（见 skills/productivity/energy-audit-imitate/references/report-format-spec.md）：
- 封面：36pt/14pt 宋体 加粗 居中
- 正文：12pt 宋体 + Times New Roman, 1.5倍行距, 首行缩进2字符, 两端对齐
- 标题：15pt 宋体 居中 / 14pt 宋体 左对齐 / 12pt 宋体 左对齐
- 目录：黑体 18pt 居中 + TOC 域；水印为被审计单位全称（DrawingML）
- 表格：12pt 宋体，行高 1.01cm
- 数字/单位：数字 + 空格 + 单位（如 1234 tce）
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
import json
import re, os

from tools.energy_audit.chart_utils import setup_chart_font, chart_text


# ============================================================
# 格式常量
# ============================================================

from .format_spec import FormatSpec, FMT  # noqa: F401（兼容导入；权威定义在 format_spec.py）

CHAPTER_STRUCTURES = {
    "公共机构": [
        ("第1章", "能源审计执行概要", [
            ("1.1", "审计目的"),
            ("1.2", "审计范围"),
            ("1.3", "审计周期"),
            ("1.4", "审计内容"),
            ("1.5", "审计过程"),
            ("1.6", "审计依据"),
        ]),
        ("第2章", "公共机构概况", [
            ("2.1", "公共机构基本情况"),
            ("2.2", "建筑物概况"),
            ("2.3", "能源资源利用情况"),
        ]),
        ("第3章", "能源资源管理状况", [
            ("3.1", "能源资源管理机构职责"),
            ("3.2", "能源资源管理目标和方针"),
            ("3.3", "能源资源管理问题与成效"),
        ]),
        ("第4章", "能源资源计量及统计状况", [
            ("4.1", "能源资源计量体系"),
            ("4.2", "计量器具配备及管理"),
            ("4.3", "能源资源统计情况"),
            ("4.4", "能源资源统计成效及问题"),
        ]),
        ("第5章", "能源资源消费/消耗指标分析", [
            ("5.1", "能源资源消费/消耗概况"),
            ("5.2", "能源资源消耗/消费数据"),
            ("5.3", "能耗资源消耗/消费指标"),
        ]),
        ("第6章", "主要能源资源利用系统分析", [
            ("6.1", "用电系统运行分析"),
            ("6.2", "用水系统运行分析"),
            ("6.3", "供暖系统运行分析"),
            ("6.4", "其他用能系统运行分析"),
            ("6.5", "室内环境检测"),
        ]),
        ("第7章", "节能效果与节能潜力分析", [
            ("7.1", "用能系统现状分析"),
            ("7.2", "节能潜力分析及建议"),
        ]),
        ("第8章", "审计结论", [
            ("8.1", "审计主要发现"),
            ("8.2", "能源利用评价"),
            ("8.3", "节能建议"),
            ("8.4", "后续工作建议"),
        ]),
    ],
    "公共建筑": [
        ("第1章", "审计执行概要", [("1.1", "审计目的"), ("1.2", "审计范围"), ("1.3", "审计依据"), ("1.4", "审计方法"), ("1.5", "主要结论")]),
        ("第2章", "建筑概况", [("2.1", "基本信息"), ("2.2", "建筑信息"), ("2.3", "用能人数"), ("2.4", "主要用能设备")]),
        ("第3章", "能源管理状况", [("3.1", "能源管理组织架构"), ("3.2", "能源管理制度"), ("3.3", "能源管理人员"), ("3.4", "能源管理培训")]),
        ("第4章", "能源计量与统计", [("4.1", "能源计量器具配置"), ("4.2", "能源统计方法"), ("4.3", "能源数据记录"), ("4.4", "能源数据报送")]),
        ("第5章", "能源消耗分析", [("5.1", "能源消费结构"), ("5.2", "能源消耗总量"), ("5.3", "人均能耗指标"), ("5.4", "单位面积能耗指标"), ("5.5", "同比环比分析")]),
        ("第6章", "能源系统分析", [("6.1", "电力系统分析"), ("6.2", "供暖系统分析"), ("6.3", "空调系统分析"), ("6.4", "照明系统分析"), ("6.5", "其他用能系统分析")]),
        ("第7章", "节能潜力分析", [("7.1", "已实施节能措施效果"), ("7.2", "节能潜力分析"), ("7.3", "节能改造建议"), ("7.4", "预期节能效果")]),
        ("第8章", "审计结论与建议", [("8.1", "审计主要发现"), ("8.2", "能源利用评价"), ("8.3", "节能建议"), ("8.4", "后续工作建议")]),
    ],
    "工业企业": [
        ("第1章", "审计执行概要", [("1.1", "审计目的"), ("1.2", "审计范围"), ("1.3", "审计依据"), ("1.4", "审计方法"), ("1.5", "主要结论")]),
        ("第2章", "企业概况", [("2.1", "基本信息"), ("2.2", "建筑信息"), ("2.3", "用能人数"), ("2.4", "主要用能设备")]),
        ("第3章", "能源管理状况", [("3.1", "能源管理组织架构"), ("3.2", "能源管理制度"), ("3.3", "能源管理人员"), ("3.4", "能源管理培训")]),
        ("第4章", "能源计量与统计", [("4.1", "能源计量器具配置"), ("4.2", "能源统计方法"), ("4.3", "能源数据记录"), ("4.4", "能源数据报送")]),
        ("第5章", "能源消耗分析", [("5.1", "能源消费结构"), ("5.2", "能源消耗总量"), ("5.3", "人均能耗指标"), ("5.4", "单位面积能耗指标"), ("5.5", "同比环比分析")]),
        ("第6章", "主要用能系统分析", [("6.1", "电力系统分析"), ("6.2", "供暖系统分析"), ("6.3", "空调系统分析"), ("6.4", "照明系统分析"), ("6.5", "其他用能系统分析")]),
        ("第7章", "节能潜力分析", [("7.1", "已实施节能措施效果"), ("7.2", "节能潜力分析"), ("7.3", "节能改造建议"), ("7.4", "预期节能效果")]),
        ("第8章", "审计结论与建议", [("8.1", "审计主要发现"), ("8.2", "能源利用评价"), ("8.3", "节能建议"), ("8.4", "后续工作建议")]),
    ],
}


# ============================================================
# Word 报告生成器
# ============================================================

class WordReportBuilder:
    """生成符合格式规范的 Word (.docx) 能源审计报告"""

    def __init__(self, audit_type: str):
        self.audit_type = audit_type
        self.chapters = CHAPTER_STRUCTURES.get(audit_type, CHAPTER_STRUCTURES["公共机构"])
        self.report_data: Dict = {}
        self.doc = None
        from docx import Document
        from docx.shared import Pt, Cm, Inches, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml.ns import qn
        self.Document = Document
        self.Pt = Pt
        self.Cm = Cm
        self.WD_ALIGN = WD_ALIGN_PARAGRAPH
        self.RGBColor = RGBColor
        self.qn = qn

    def set_data(self, data: Dict):
        """设置报告数据"""
        self.report_data = data

    def _set_font(self, run, cn_font: str, en_font: str, size_pt: int, bold: bool = False):
        """设置 run 的字体属性（直接操作 XML 确保可靠）"""
        from lxml import etree as _etree
        from docx.oxml.ns import qn as _qn
        rPr = run._element.get_or_add_rPr()

        # 字号 (w:sz = half-points, w:szCs = complex script)
        sz = rPr.find(_qn('w:sz'))
        if sz is None:
            sz = _etree.SubElement(rPr, _qn('w:sz'))
        sz.set(_qn('w:val'), str(size_pt * 2))
        szCs = rPr.find(_qn('w:szCs'))
        if szCs is None:
            szCs = _etree.SubElement(rPr, _qn('w:szCs'))
        szCs.set(_qn('w:val'), str(size_pt * 2))

        # 加粗
        if bold:
            if rPr.find(_qn('w:b')) is None:
                _etree.SubElement(rPr, _qn('w:b'))

        # 字体
        rFonts = rPr.find(_qn('w:rFonts'))
        if rFonts is None:
            rFonts = _etree.SubElement(rPr, _qn('w:rFonts'))
        rFonts.set(_qn('w:ascii'), en_font)
        rFonts.set(_qn('w:hAnsi'), en_font)
        rFonts.set(_qn('w:eastAsia'), cn_font)

    def _set_paragraph_format(self, para, line_spacing: float, alignment: int,
                              first_line_indent_chars: float = 0,
                              space_before: int = 0, space_after: int = 0):
        """设置段落格式"""
        from docx.shared import Pt as _Pt
        pf = para.paragraph_format
        pf.line_spacing = line_spacing
        pf.alignment = alignment
        if first_line_indent_chars > 0:
            # 首行缩进 = 字号(pt) × 缩进字符数
            pf.first_line_indent = _Pt(FMT.body_size * first_line_indent_chars)
        if space_before > 0:
            pf.space_before = _Pt(space_before)
        if space_after > 0:
            pf.space_after = _Pt(space_after)

    def _add_body_text(self, text: str):
        """添加正文段落（12pt 宋体 + Times New Roman, 1.5倍行距, 首行缩进2字符, 两端对齐）"""
        if not text:
            return
        para = self.doc.add_paragraph()
        self._set_paragraph_format(para, FMT.body_line_spacing, FMT.body_alignment,
                                   FMT.body_first_line_indent)
        run = para.add_run(text)
        self._set_font(run, FMT.body_font_cn, FMT.body_font_en, FMT.body_size)

    def _add_formula(self, formula_text: str):
        """插入OMML公式（Word数学公式格式，分数线+斜体变量+下标）"""
        from lxml import etree
        from docx.oxml.ns import qn

        para = self.doc.add_paragraph()
        self._set_paragraph_format(para, FMT.body_line_spacing, FMT.body_alignment,
                                   FMT.body_first_line_indent)

        M = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
        oMath = etree.SubElement(para._element, qn('m:oMath'), nsmap={'m': M})

        def _add_math_run(parent, text, is_var=False):
            r = etree.SubElement(parent, qn('m:r'))
            if is_var:
                rPr = etree.SubElement(r, qn('m:rPr'))
                sty = etree.SubElement(rPr, qn('m:sty'))
                sty.set(qn('m:val'), 'p')
            t = etree.SubElement(r, qn('m:t'))
            t.text = str(text)
            t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')

        def _add_sub(parent, base, sub):
            """添加带下标的变量：E_jrcn, E_gn, E_jt"""
            sSub = etree.SubElement(parent, qn('m:sSub'))
            e = etree.SubElement(sSub, qn('m:e'))
            _add_math_run(e, base, is_var=True)
            sub_e = etree.SubElement(sSub, qn('m:sub'))
            _add_math_run(sub_e, sub, is_var=True)

        # E_jrcn =
        _add_sub(oMath, 'E', 'jrcn')
        _add_math_run(oMath, ' = ')

        # 分数线 (E - E_gn - E_jt) / M
        frac = etree.SubElement(oMath, qn('m:f'))
        etree.SubElement(frac, qn('m:fPr'))
        num = etree.SubElement(frac, qn('m:num'))
        den = etree.SubElement(frac, qn('m:den'))

        _add_math_run(num, '(')
        _add_math_run(num, 'E', is_var=True)
        _add_math_run(num, ' - ')
        _add_sub(num, 'E', 'gn')
        _add_math_run(num, ' - ')
        _add_sub(num, 'E', 'jt')
        _add_math_run(num, ')')

        _add_math_run(den, 'M', is_var=True)

    def _add_simple_fraction_formula(self, result_var: str, num_var: str, den_var: str):
        """插入简单分数 OMML 公式：result_var = num_var / den_var（支持下标的变量名如 E_ja）"""
        from lxml import etree
        from docx.oxml.ns import qn

        para = self.doc.add_paragraph()
        self._set_paragraph_format(para, FMT.body_line_spacing, FMT.body_alignment,
                                   FMT.body_first_line_indent)

        M = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
        oMath = etree.SubElement(para._element, qn('m:oMath'), nsmap={'m': M})

        def _add_math_run(parent, text, is_var=False):
            r = etree.SubElement(parent, qn('m:r'))
            if is_var:
                rPr = etree.SubElement(r, qn('m:rPr'))
                sty = etree.SubElement(rPr, qn('m:sty'))
                sty.set(qn('m:val'), 'p')
            t = etree.SubElement(r, qn('m:t'))
            t.text = str(text)
            t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')

        def _add_sub_var(parent, var_str):
            """解析 E_ja → E 带下标 ja"""
            parts = var_str.split('_', 1)
            if len(parts) == 2:
                sSub = etree.SubElement(parent, qn('m:sSub'))
                e = etree.SubElement(sSub, qn('m:e'))
                _add_math_run(e, parts[0], is_var=True)
                sub_e = etree.SubElement(sSub, qn('m:sub'))
                _add_math_run(sub_e, parts[1], is_var=True)
            else:
                _add_math_run(parent, var_str, is_var=True)

        # result_var =
        _add_sub_var(oMath, result_var)
        _add_math_run(oMath, ' = ')

        # 分数线 num_var / den_var
        frac = etree.SubElement(oMath, qn('m:f'))
        etree.SubElement(frac, qn('m:fPr'))
        num = etree.SubElement(frac, qn('m:num'))
        den = etree.SubElement(frac, qn('m:den'))

        _add_sub_var(num, num_var)
        _add_sub_var(den, den_var)

    def _add_formula_symbol(self, symbol: str, description: str):
        """插入公式符号说明行：斜体变量（含下标）+ 正体中文描述"""
        para = self.doc.add_paragraph()
        self._set_paragraph_format(para, FMT.body_line_spacing, FMT.body_alignment,
                                   FMT.body_first_line_indent)

        # 解析 symbol 中的下划线：E_jrcn——  → E(italic) + subscript jrcn + ——description
        import re
        parts = re.split(r'(——)', symbol, 1)
        var_part = parts[0]  # e.g. "E_jrcn" or "M"
        sep = parts[1] if len(parts) > 1 else ''

        # 解析变量名中的下标
        var_match = re.match(r'([A-Za-z]+)_([a-z]+)', var_part)
        if var_match:
            # 有下标
            base = var_match.group(1)
            sub = var_match.group(2)
            run_base = para.add_run(base)
            self._set_font(run_base, FMT.body_font_cn, FMT.body_font_en, FMT.body_size)
            run_base.italic = True
            run_sub = para.add_run(sub)
            self._set_font(run_sub, FMT.body_font_cn, FMT.body_font_en, FMT.body_size)
            run_sub.italic = True
            run_sub.font.subscript = True
        else:
            # 无下标
            run_var = para.add_run(var_part)
            self._set_font(run_var, FMT.body_font_cn, FMT.body_font_en, FMT.body_size)
            run_var.italic = True

        if sep:
            run_sep = para.add_run(sep)
            self._set_font(run_sep, FMT.body_font_cn, FMT.body_font_en, FMT.body_size)

        run_desc = para.add_run(description)
        self._set_font(run_desc, FMT.body_font_cn, FMT.body_font_en, FMT.body_size)

    def _add_bullet_text(self, text: str):
        """添加无序列表项：实心圆点 + 12pt 宋体，1.5倍行距"""
        if not text:
            return
        para = self.doc.add_paragraph()
        self._set_paragraph_format(para, FMT.body_line_spacing, FMT.body_alignment)
        run = para.add_run("● " + text)
        self._set_font(run, FMT.body_font_cn, FMT.body_font_en, FMT.body_size)

    def _set_outline_level(self, para, level: int):
        """Word 大纲级别（0=章），供目录域收录。"""
        from lxml import etree
        from docx.oxml.ns import qn as _qn
        pPr = para._p.get_or_add_pPr()
        el = pPr.find(_qn("w:outlineLvl"))
        if el is None:
            el = etree.SubElement(pPr, _qn("w:outlineLvl"))
        el.set(_qn("w:val"), str(level))

    def _add_heading_1(self, text: str):
        """一级标题：小三号(15pt) 宋体 加粗 居中。"""
        para = self.doc.add_paragraph()
        self._set_paragraph_format(para, FMT.h1_line_spacing, FMT.h1_alignment,
                                   space_before=FMT.h1_space_before, space_after=FMT.h1_space_after)
        run = para.add_run(text)
        self._set_font(run, FMT.h1_font, FMT.body_font_en, FMT.h1_size, bold=FMT.h1_bold)
        self._set_outline_level(para, 0)

    def _add_heading_2(self, text: str):
        """二级标题：四号(14pt) 宋体 加粗 左对齐。"""
        para = self.doc.add_paragraph()
        self._set_paragraph_format(para, FMT.h2_line_spacing, FMT.h2_alignment,
                                   space_before=FMT.h2_space_before, space_after=FMT.h2_space_after)
        run = para.add_run(text)
        self._set_font(run, FMT.h2_font, FMT.body_font_en, FMT.h2_size, bold=FMT.h2_bold)
        self._set_outline_level(para, 1)

    def _add_heading_3(self, text: str):
        """三级标题：12pt 宋体 加粗 左对齐。"""
        para = self.doc.add_paragraph()
        self._set_paragraph_format(para, FMT.h3_line_spacing, FMT.h3_alignment)
        run = para.add_run(text)
        self._set_font(run, FMT.h3_font, FMT.body_font_en, FMT.h3_size, bold=FMT.h3_bold)
        self._set_outline_level(para, 2)

    def _add_table(self, headers: List[str], rows: List[List[str]], title: str = None):
        """添加表格：标题12pt 宋体 加粗 居中，内容12pt 宋体 居中，行高 1.01cm，上下居中"""
        if title:
            para = self.doc.add_paragraph()
            para.alignment = self.WD_ALIGN.CENTER
            run = para.add_run(title)
            self._set_font(run, FMT.body_font_cn, FMT.body_font_en, FMT.table_header_size, bold=True)

        from docx.shared import Cm as _Cm
        from docx.enum.table import WD_ROW_HEIGHT_RULE, WD_TABLE_ALIGNMENT
        from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT

        table = self.doc.add_table(rows=1 + len(rows), cols=len(headers), style='Table Grid')
        table.autofit = False
        table.alignment = WD_TABLE_ALIGNMENT.CENTER

        # 行高 1.01cm
        for row in table.rows:
            row.height = _Cm(1.01)
            row.height_rule = WD_ROW_HEIGHT_RULE.EXACTLY

        # Header
        for i, h in enumerate(headers):
            cell = table.rows[0].cells[i]
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            p = cell.paragraphs[0]
            p.clear()
            p.alignment = self.WD_ALIGN.CENTER
            r = p.add_run(h)
            self._set_font(r, FMT.body_font_cn, FMT.body_font_en, FMT.table_header_size, bold=True)
        # Data rows
        for ri, row_data in enumerate(rows):
            row = table.rows[ri + 1]
            for ci, val in enumerate(row_data):
                cell = row.cells[ci]
                cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                p = cell.paragraphs[0]
                p.clear()
                p.alignment = self.WD_ALIGN.CENTER
                r = p.add_run(str(val))
                self._set_font(r, FMT.body_font_cn, FMT.body_font_en, FMT.table_content_size)

    def _add_table_title(self, text: str):
        """表格标题：宋体 小四号(12pt) 加粗 居中"""
        para = self.doc.add_paragraph()
        para.alignment = self.WD_ALIGN.CENTER
        run = para.add_run(text)
        self._set_font(run, FMT.body_font_cn, FMT.body_font_en, FMT.table_header_size, bold=True)

    def _add_page_break(self):
        from docx.oxml.ns import qn
        self.doc.add_page_break()

    # ============================================================
    # 各章节生成
    # ============================================================

    def build_audit_info_tables(self):
        """审计基本信息三张表：机构信息表、审计组人员名单、配合人员名单（10.5pt 宋体 单倍行距）"""
        tables_data = self.report_data.get('audit_info_tables', {})

        # ---- 表1：能源审计机构信息表 ----
        self._add_table_title("能源审计机构信息表")
        inst = tables_data.get('institution', {})
        self._add_two_col_table(
            ["项  目", "内  容"],
            [
                ["机构名称", inst.get('name', '⚠️ 请提供被审计单位全称。')],
                ["地  址", inst.get('address', '⚠️ 请提供单位详细地址。')],
                ["负 责 人", inst.get('contact', '⚠️ 请提供负责人姓名。')],
                ["联系方式", inst.get('phone', '⚠️ 请提供联系电话。')],
            ]
        )

        # ---- 表2：能源审计组人员名单 ----
        self._add_table_title("能源审计组人员名单")
        members = tables_data.get('team_members', [])
        headers = ["组内职务", "姓  名", "学  历", "所获资质", "专  业"]
        rows = [[m.get(k, '') for k in ['role','name','education','certification','major']] for m in members] if members else [
            ["⚠️ 请提供审计组人员名单（姓名/学历/资质/专业）","","","",""]
        ]
        self._add_table(headers, rows)

        # ---- 表3：能源审计配合人员名单 ----
        self._add_table_title("能源审计配合人员名单")
        coop = tables_data.get('cooperation', [])
        headers = ["组内职务", "部  门", "姓  名", "性  别", "职  务"]
        rows = [[c.get(k, '') for k in ['role','dept','name','gender','position']] for c in coop] if coop else [
            ["⚠️ 请提供配合人员名单（部门/姓名/性别/职务）","","","",""]
        ]
        self._add_table(headers, rows)

    def _add_two_col_table(self, headers, rows):
        """添加两列表格（标题+内容格式），标题列加粗居中，内容列居中，行高 1.01cm，上下居中"""
        from docx.shared import Cm as _Cm
        from docx.enum.table import WD_ROW_HEIGHT_RULE, WD_TABLE_ALIGNMENT
        from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT

        table = self.doc.add_table(rows=len(rows), cols=2, style='Table Grid')
        table.autofit = False
        table.alignment = WD_TABLE_ALIGNMENT.CENTER

        # 行高 1.01cm
        for row in table.rows:
            row.height = _Cm(1.01)
            row.height_rule = WD_ROW_HEIGHT_RULE.EXACTLY
        for ri, row_data in enumerate(rows):
            row = table.rows[ri]
            for ci, val in enumerate(row_data):
                cell = row.cells[ci]
                cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                p = cell.paragraphs[0]
                p.clear()
                p.alignment = self.WD_ALIGN.CENTER
                r = p.add_run(str(val))
                if ci == 0:
                    self._set_font(r, FMT.body_font_cn, FMT.body_font_en, FMT.table_content_size, bold=True)
                else:
                    self._set_font(r, FMT.body_font_cn, FMT.body_font_en, FMT.table_content_size)
        self.doc.add_paragraph()

    def build_cover(self):
        """封面"""
        cover = self.report_data.get('cover', {})
        unit_name = cover.get('title', '')
        # 提取被审计单位名称（去掉"能源审计报告"后缀）
        if '能源审计报告' in unit_name:
            unit_name = unit_name.replace('能源审计报告', '').strip()

        # 顶部留白
        for _ in range(2):
            self.doc.add_paragraph()
        para = self.doc.add_paragraph()
        para.alignment = self.WD_ALIGN.CENTER
        run = para.add_run(unit_name)
        self._set_font(run, FMT.body_font_cn, FMT.body_font_en, FMT.cover_title_size, bold=True)

        # "能源审计报告"：36pt 宋体 加粗 居中
        para = self.doc.add_paragraph()
        para.alignment = self.WD_ALIGN.CENTER
        run = para.add_run("能源审计报告")
        self._set_font(run, FMT.body_font_cn, FMT.body_font_en, FMT.cover_title_size, bold=True)

        # 底部信息：通过审计机构的段前间距推到页面下部
        audit_org = cover.get('audit_organization', '')
        para = self.doc.add_paragraph()
        para.alignment = self.WD_ALIGN.CENTER
        para.paragraph_format.space_before = self.Pt(420)  # 推到页面下部
        run = para.add_run(audit_org)
        self._set_font(run, FMT.body_font_cn, FMT.body_font_en, FMT.cover_info_size, bold=True)

        self.doc.add_paragraph()

        # 日期：14pt 宋体 加粗 居中（YYYY年M月）
        date_str = cover.get('report_date', datetime.now().strftime('%Y年%m月'))
        # 转换为 YYYY年M月 格式
        try:
            dt = datetime.strptime(date_str, '%Y年%m月%d日')
            date_str = dt.strftime('%Y年%m月').replace('年0', '年').replace('月0', '月')
        except Exception:
            pass
        para = self.doc.add_paragraph()
        para.alignment = self.WD_ALIGN.CENTER
        run = para.add_run(date_str)
        self._set_font(run, FMT.body_font_cn, FMT.body_font_en, FMT.cover_info_size, bold=True)

        self._add_page_break()

    def build_toc(self):
        """目录：黑体 小二号(18pt) 加粗 居中 + Word TOC 域。"""
        from lxml import etree
        from docx.oxml.ns import qn as _qn

        para = self.doc.add_paragraph()
        para.alignment = self.WD_ALIGN.CENTER
        para.paragraph_format.line_spacing = 1.5
        run = para.add_run("目  录")
        self._set_font(run, "黑体", FMT.body_font_en, 18, bold=True)

        field = self.doc.add_paragraph()
        field.paragraph_format.line_spacing = 1.5
        r = field.add_run()._r
        begin = etree.SubElement(r, _qn("w:fldChar"))
        begin.set(_qn("w:fldCharType"), "begin")
        instr_run = field.add_run()._r
        instr = etree.SubElement(instr_run, _qn("w:instrText"))
        instr.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        instr.text = ' TOC \\o "1-2" \\h \\z \\u '
        sep_run = field.add_run()._r
        separate = etree.SubElement(sep_run, _qn("w:fldChar"))
        separate.set(_qn("w:fldCharType"), "separate")
        hint = field.add_run("（目录将在 Word/WPS 打开时自动生成；若未显示请按 Ctrl+A 后 F9 更新域）")
        self._set_font(hint, FMT.body_font_cn, FMT.body_font_en, FMT.body_size)
        end_run = field.add_run()._r
        end = etree.SubElement(end_run, _qn("w:fldChar"))
        end.set(_qn("w:fldCharType"), "end")

        self._add_page_break()

    def build_all_chapters(self):
        """仅支持仿写模式（imitated_chapters）渲染。

        8 章正文硬编码生成已于 2026-09-04 退役——报告正文由 author 按
        ea-authoring 技能逐章 LLM 写作 + office_editor 组装，脚本不写正文。
        """
        if self.report_data.get("generation_mode") == "imitate" or self.report_data.get("imitated_chapters"):
            self._build_imitated_chapters()
            return
        raise RuntimeError(
            "报告正文生成已退役（2026-09-04）：请按 ea-authoring 技能逐章写作，"
            "用 office_editor 工具集组装 Word。本脚本仅支持仿写模式（imitated_chapters）。"
        )

    _IMITATED_H1 = re.compile(r"^第[1-8一二三四五六七八]章")
    _IMITATED_H3 = re.compile(r"^\d+\.\d+\.\d+\s+\S")
    _IMITATED_H2 = re.compile(r"^\d+\.\d+\s+\S")

    def _imitated_chapter_text(self, chapter_key: str) -> str:
        raw = (self.report_data.get("imitated_chapters") or {}).get(chapter_key)
        if isinstance(raw, dict):
            return (raw.get("text") or "").strip()
        return (raw or "").strip()

    def _write_imitated_body(self, text: str):
        """把仿写正文写入 Word：识别 1.1 / 1.1.1 为标题，跳过重复的章标题。

        支持 markdown 表格（`| a | b |` 行，首行为表头，分隔行 `|---|` 忽略），
        以及表格标题行（以"表X.Y"开头的行）——渲染为规范表格（12pt 居中、行高 1.01cm）。
        支持图表标记行 `[[图:类型|图注]]`：按 chart_data 渲染并嵌入图片。
        """
        lines = (text or "").replace("\r\n", "\n").split("\n")
        pending_title = None  # 待绑定的表格标题
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                pending_title = None
                i += 1
                continue
            # 图表标记：[[图:类型|图注]] —— 渲染图表并嵌入
            if line.startswith("[[图:") and line.endswith("]]"):
                img_path = self._render_imitated_chart(line)
                if img_path:
                    caption = line[line.find("|")+1:-2].strip() if "|" in line else ""
                    self._add_image_with_caption(img_path, caption)
                pending_title = None
                i += 1
                continue
            # 表格标题行（表X.Y 开头）——预留给后续表格块
            if re.match(r"^表\d+\.\d+", line) and len(line) < 80:
                # 若该行后紧跟表格块则作为表格标题，否则作为正文（如"表5.1 所示"）
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines) and lines[j].strip().startswith("|"):
                    pending_title = line
                    i += 1
                    continue
            # markdown 表格块：连续 | 行
            if line.startswith("|") and line.endswith("|"):
                table_lines = []
                while i < len(lines) and lines[i].strip().startswith("|") and lines[i].strip().endswith("|"):
                    table_lines.append(lines[i].strip())
                    i += 1
                rows = []
                for tl in table_lines:
                    cells = [c.strip() for c in tl.strip("|").split("|")]
                    if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                        continue  # markdown 分隔行
                    rows.append(cells)
                if rows:
                    self._add_table(rows[0], rows[1:], title=pending_title)
                    pending_title = None
                continue
            if self._IMITATED_H1.match(line) and len(line) < 80:
                pending_title = None
                i += 1
                continue
            if self._IMITATED_H3.match(line) and len(line) < 80:
                pending_title = None
                self._add_heading_3(line)
            elif self._IMITATED_H2.match(line) and len(line) < 80:
                pending_title = None
                self._add_heading_2(line)
            else:
                pending_title = None
                self._add_body_text(line)
            i += 1

    def _render_imitated_chart(self, marker: str):
        """渲染仿写正文中的图表标记 [[图:类型|图注]]。

        类型支持：trend（逐年趋势）、pie（能源结构饼图）、
        monthly_电/monthly_水/monthly_气（逐月柱状图）、flow（能源流向图）。
        数据来自 report_data['chart_data']，缺数据或渲染失败时返回 None（静默跳过）。
        """
        inner = marker[4:-2].strip()
        chart_type = inner.split("|")[0].strip().lower()
        chart_data = self.report_data.get("chart_data") or {}
        years_data = chart_data.get("years") or []
        if not years_data:
            return None
        output_dir = chart_data.get("output_dir") or os.path.join(os.getcwd(), "charts")
        os.makedirs(output_dir, exist_ok=True)
        try:
            if chart_type in ("trend", "pie"):
                from tools.energy_audit.indicators import YearlyEnergyData
                yd_objects = []
                for d in years_data:
                    yd_objects.append(YearlyEnergyData(
                        year=int(d.get("year", 0)),
                        electricity_kwh=float(d.get("electricity_kwh", 0) or 0),
                        water_m3=float(d.get("water_m3", 0) or 0),
                        natural_gas_m3=float(d.get("natural_gas_m3", 0) or 0),
                        heating_energy_heat=float(d.get("heating_energy_heat_gj", 0) or 0),
                        transportation_petrol_kg=float(d.get("petrol_kg", 0) or 0),
                        transportation_diesel_kg=float(d.get("diesel_kg", 0) or 0),
                        building_area=float(chart_data.get("building_area", 0) or 0),
                        people_count=float(chart_data.get("people_count", 0) or 0),
                    ))
                energy_types = chart_data.get("energy_types") or ["electricity_kwh", "water_m3", "natural_gas_m3"]
                if chart_type == "trend":
                    return self._generate_yearly_trend_chart(yd_objects, energy_types, output_dir)
                return self._generate_energy_pie_chart(yd_objects, energy_types, output_dir)
            if chart_type == "cost_pie":
                return self._generate_cost_pie_chart(years_data, output_dir)
            if chart_type.startswith("monthly_"):
                et_key = chart_type.replace("monthly_", "")
                monthly_attr = {"electricity_kwh": "monthly_electricity_kwh",
                                "water_m3": "monthly_water_m3",
                                "natural_gas_m3": "monthly_natural_gas_m3"}.get(et_key)
                if not monthly_attr:
                    return None
                name_cn = self._ENERGY_TYPE_CN.get(et_key, et_key)
                unit = {"electricity_kwh": "kWh", "water_m3": "m³", "natural_gas_m3": "m³"}.get(et_key, "")
                return _generate_monthly_bar_chart(years_data, et_key, monthly_attr, name_cn, unit, output_dir)
            if chart_type == "flow":
                from tools.energy_audit.energy_flow_chart import draw_energy_flow_diagram
                energy_types = chart_data.get("energy_types") or ["electricity_kwh", "water_m3", "natural_gas_m3"]
                # 时间戳文件名：避免与用户已打开的旧图（文件锁）冲突
                flow_path = os.path.join(output_dir, f"energy_flow_{int(__import__('time').time())}.png")
                return draw_energy_flow_diagram(
                    energy_types=energy_types,
                    equipment=chart_data.get("equipment"),
                    unit_name=chart_data.get("unit_name", ""),
                    output_path=flow_path,
                ) or (flow_path if os.path.exists(flow_path) else None)
        except Exception as e:
            self._chart_errors = getattr(self, "_chart_errors", []) + [f"{chart_type}: {e}"]
            return None
        return None

    def _append_chapter_images(self, chapter_key: str):
        mapping = {"第2章": "chapter2", "第3章": "chapter3"}
        data_key = mapping.get(chapter_key)
        if not data_key:
            return
        images = self.report_data.get(data_key, {}).get("images", []) or []
        prefix = "图2" if chapter_key == "第2章" else "图3"
        for idx, img_info in enumerate(images, 1):
            path = img_info.get("path", "") if isinstance(img_info, dict) else ""
            caption = (img_info.get("caption") if isinstance(img_info, dict) else None) or f"{prefix}-{idx}"
            if path and os.path.exists(path):
                self._add_image_with_caption(path, caption)

    def _build_imitated_chapters(self):
        """仿写模式渲染：有仿写正文的章节渲染文本+图片，缺章写入占位提示。"""
        for ch_num, ch_title, _sub in self.chapters:
            text = self._imitated_chapter_text(ch_num)
            if text:
                self._add_heading_1(f"{ch_num}  {ch_title}")
                self._write_imitated_body(text)
                self._append_chapter_images(ch_num)
            else:
                self._add_heading_1(f"{ch_num}  {ch_title}")
                self._add_body_text(f"【{ch_title}：仿写正文缺失，请按 ea-authoring 技能补充写作】")

    # ============================================================
    # 第1章模板
    # ============================================================


    @staticmethod
    def _generate_cost_pie_chart(self, years_data, output_dir: str = './charts'):
        """最新年能源费用占比饼图（电费/水费/天然气费/热力费，单位：万元）"""
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            setup_chart_font(plt)
        except ImportError:
            return None

        os.makedirs(output_dir, exist_ok=True)
        latest = years_data[-1]
        cost_fields = [
            ("electricity_cost_wan", "电费"),
            ("water_cost_wan", "水费"),
            ("natural_gas_cost_wan", "天然气费"),
            ("heating_cost_wan", "热力费"),
        ]
        labels = []
        values = []
        for key, label in cost_fields:
            v = float(latest.get(key, 0) or 0)
            if v > 0:
                labels.append(label)
                values.append(v)
        if not values:
            return None
        fig, ax = plt.subplots(figsize=(6, 6))
        ax.pie(values, labels=labels, autopct='%1.1f%%', startangle=90,
               colors=['#4CAF50', '#2196F3', '#FF9800', '#F44336'])
        ax.set_title(chart_text(f'{latest.get("year", "")}年能源费用占比'))
        path = os.path.join(output_dir, 'chart_cost_structure.png')
        fig.savefig(path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        return path

    def _generate_energy_pie_chart(self, yd_objects, energy_types, output_dir: str = './charts'):
        """生成最新年能源结构的饼图"""
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            setup_chart_font(plt)
        except ImportError:
            return None

        os.makedirs(output_dir, exist_ok=True)
        latest = yd_objects[-1]
        labels = [self._ENERGY_TYPE_CN.get(et, et) for et in energy_types]
        coeff_map = {'electricity_kwh':0.1229,'water_m3':0.2571,'natural_gas_m3':1.33,'petrol_kg':1.4714,'diesel_kg':1.4571}
        values = [getattr(latest, et, 0) * coeff_map.get(et, 1) / 1000 for et in energy_types]
        if not any(v > 0 for v in values):
            return None
        fig, ax = plt.subplots(figsize=(6, 6))
        ax.pie(values, labels=labels, autopct='%1.1f%%', startangle=90)
        ax.set_title(chart_text(f'{latest.year}年能源消费结构'))
        path = os.path.join(output_dir, 'chart_structure.png')
        fig.savefig(path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        return path

    def _generate_yearly_trend_chart(self, yd_objects, energy_types, output_dir: str = './charts'):
        """逐年能耗趋势柱状图"""
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            setup_chart_font(plt)
        except ImportError:
            return None

        os.makedirs(output_dir, exist_ok=True)
        years = [str(yd.year) for yd in yd_objects]
        # 只显示 top 3 能源类型
        coeff_map = {'electricity_kwh':0.1229,'water_m3':0.2571,'natural_gas_m3':1.33,'petrol_kg':1.4714,'diesel_kg':1.4571}
        et_values = {}
        for et in energy_types:
            vals = [getattr(yd, et, 0) * coeff_map.get(et, 1) / 1000 for yd in yd_objects]
            if any(v > 0 for v in vals):
                et_values[et] = vals
        if not et_values:
            return None

        fig, ax = plt.subplots(figsize=(8, 5))
        x = range(len(years))
        width = 0.8 / len(et_values)
        for i, (et, vals) in enumerate(et_values.items()):
            ax.bar([xi + i*width for xi in x], vals, width, label=self._ENERGY_TYPE_CN.get(et, et))
        ax.set_xticks([xi + width*(len(et_values)-1)/2 for xi in x])
        ax.set_xticklabels(years)
        ax.set_ylabel('tce')
        ax.set_title(chart_text('逐年能耗趋势'))
        ax.legend()
        ax.grid(True, alpha=0.3, axis='y')
        path = os.path.join(output_dir, 'chart_trend.png')
        fig.savefig(path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        return path

    def _add_image_with_caption(self, image_path: str, caption: str):
        """嵌入图片（宽度12cm，居中），下方居中添加图注（12pt 宋体，1.5倍行距，居中）"""
        from docx.shared import Cm as _Cm
        para = self.doc.add_paragraph()
        para.alignment = self.WD_ALIGN.CENTER
        try:
            run = para.add_run()
            run.add_picture(image_path, width=_Cm(12))
        except Exception as e:
            run = para.add_run(f"[图片无法嵌入: {e}]")
            self._set_font(run, FMT.body_font_cn, FMT.body_font_en, 10)

        # 图注（12pt 宋体，1.5倍行距，居中）
        cap_para = self.doc.add_paragraph()
        cap_para.alignment = self.WD_ALIGN.CENTER
        cap_para.paragraph_format.line_spacing = FMT.body_line_spacing
        cap_run = cap_para.add_run(caption)
        self._set_font(cap_run, FMT.body_font_cn, FMT.body_font_en, FMT.body_size)

    def generate(self, output_path: str):
        """生成 Word 报告（含目录自动更新与水印）"""
        self.doc = self.Document()

        # 页面设置
        from docx.shared import Cm
        section = self.doc.sections[0]
        section.page_width = Cm(21)
        section.page_height = Cm(29.7)
        section.top_margin = Cm(2.54)
        section.bottom_margin = Cm(2.54)
        section.left_margin = Cm(3.17)
        section.right_margin = Cm(3.17)

        self.build_cover()
        self.build_audit_info_tables()
        self.build_toc()
        self.build_all_chapters()

        self.doc.save(output_path)

        # 目录域自动更新：Word 打开时刷新 TOC/页码
        self._set_update_fields_on_open(output_path)
        # 页脚页码：第 X 页 共 Y 页
        self._add_page_numbers(output_path)
        return output_path

    def _add_page_numbers(self, output_path: str):
        """向页脚写入居中页码域：第 X 页 共 Y 页（Word/WPS 打开时随 updateFields 自动刷新）。"""
        from docx import Document as _Doc
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn as _qn
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        doc = _Doc(output_path)
        sec = doc.sections[0]
        footer = sec.footer
        # 复用/清空默认页脚段落
        if footer.paragraphs:
            p = footer.paragraphs[0]
            for r in list(p.runs):
                r._r.getparent().remove(r._r)
        else:
            p = footer.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER

        def _set_font_run(run, size=10.5, bold=False):
            run.font.name = "Times New Roman"
            run.font.size = self.Pt(size)
            run.font.bold = bold
            rPr = run._r.get_or_add_rPr()
            rFonts = rPr.find(_qn("w:rFonts"))
            if rFonts is None:
                from lxml import etree as _etree
                rFonts = _etree.SubElement(rPr, _qn("w:rFonts"))
            rFonts.set(_qn("w:eastAsia"), "宋体")

        def _add_field(fld_type: str):
            """插入 PAGE / NUMPAGES 域"""
            run = p.add_run()
            _set_font_run(run)
            r = run._r
            b = OxmlElement("w:fldChar"); b.set(_qn("w:fldCharType"), "begin")
            instr = OxmlElement("w:instrText"); instr.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            instr.text = f" {fld_type} "
            s = OxmlElement("w:fldChar"); s.set(_qn("w:fldCharType"), "separate")
            t = OxmlElement("w:t"); t.text = "1"
            e = OxmlElement("w:fldChar"); e.set(_qn("w:fldCharType"), "end")
            r.append(b); r.append(instr); r.append(s); r.append(t); r.append(e)

        r1 = p.add_run("第 "); _set_font_run(r1)
        _add_field("PAGE")
        r2 = p.add_run(" 页 共 "); _set_font_run(r2)
        _add_field("NUMPAGES")
        r3 = p.add_run(" 页"); _set_font_run(r3)

        doc.save(output_path)

    def _set_update_fields_on_open(self, output_path: str):
        """在 word/settings.xml 写入 <w:updateFields w:val="true"/>，使 Word 打开时自动刷新目录域。"""
        import tempfile
        import zipfile
        import shutil
        from pathlib import Path
        from lxml import etree

        W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        tmp = Path(tempfile.mkdtemp(prefix="ea_updatefields_"))
        try:
            with zipfile.ZipFile(output_path, "r") as z:
                z.extractall(tmp)
            settings = tmp / "word" / "settings.xml"
            settings.parent.mkdir(parents=True, exist_ok=True)
            if settings.exists():
                tree = etree.parse(str(settings))
                root = tree.getroot()
            else:
                root = etree.Element(f"{{{W_NS}}}settings")
                tree = etree.ElementTree(root)
            uf = root.find(f"{{{W_NS}}}updateFields")
            if uf is None:
                uf = etree.Element(f"{{{W_NS}}}updateFields")
                root.insert(0, uf)
            uf.set(f"{{{W_NS}}}val", "true")
            tree.write(str(settings), xml_declaration=True, encoding="UTF-8", standalone="yes")
            with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
                for f in tmp.rglob("*"):
                    if f.is_dir():
                        continue
                    z.write(f, f.relative_to(tmp).as_posix())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class ReportGenerator:
    """能源审计报告生成器（支持 Word 和 Markdown）"""

    def __init__(self, audit_type: str):
        self.audit_type = audit_type
        self.report_data: Dict = {}
        self.word_builder = WordReportBuilder(audit_type)

    def set_report_data(self, data: Dict):
        self.report_data = data
        self.word_builder.set_data(data)

    def _query_basic_situation_fallback(self, unit_name: str) -> str:
        """2.1 兜底：项目数据无 basic_situation 时，从 PG ts_customer_info 反查。

        链路: find_project_by_name(unit_name) → customer_id →
              get_customer_info(customer_id) → basic_situation
        任何一步失败/无数据都返回 ''（不抛异常，避免生成报告被 DB 故障阻断）。
        """
        if not unit_name:
            return ''
        try:
            from tools.energy_audit import PgDataQuery
            pg = PgDataQuery()
            pg.connect()
            try:
                proj = pg.find_project_by_name(unit_name)
                customer_id = proj.get('customer_id') if proj else None
                if not customer_id:
                    return ''
                cust = pg.get_customer_info(customer_id=customer_id)
                if cust and cust[0].get('basic_situation'):
                    return str(cust[0]['basic_situation'])
                return ''
            finally:
                pg.disconnect()
        except Exception:
            return ''

    def load_from_project(self, project) -> Dict:
        """从 AuditProject 自动构建 report_data（字段溯源: project_data → 用户 → 默认）"""
        from tools.energy_audit.project_data import AuditProject
        if not isinstance(project, AuditProject):
            raise TypeError("需要 AuditProject 对象")

        b = project.base

        # ---- 照片按分类路由（对齐 photo_manager.PHOTO_REQUIREMENTS）----
        # 未分类照片（category=''）兜底进第2章；分类照片按章节/系统分发。
        img_by_cat: Dict[str, List] = {}
        for _img in project.images:
            _cat = getattr(_img, 'category', '') or ''
            img_by_cat.setdefault(_cat, []).append(_img)

        def _chapter_imgs(*cats: str, prefix: str = '图2') -> List[Dict]:
            """取指定分类的照片 → [{path, caption}]；caption 未填时按章节自动编号"""
            items = []
            for c in cats:
                items.extend(img_by_cat.get(c, []))
            return [{'path': _i.path, 'caption': _i.caption or f'{prefix}-{idx+1}'}
                    for idx, _i in enumerate(items)]

        # 第3章：管理信息 + 节能管理信息（ts_institution_energy_saving）合并，
        # 节能管理信息有记录时用真实数据生成，无记录时保留既有兜底文案。
        chapter3 = {
            'section_3_1': project.management.management_org or '',
            # 3.2 目标与方针：优先用 LLM 从制度文件提炼的正文，否则留空由兜底文案补
            'section_3_2': project.management.management_policy or '',
            'section_3_3': project.management.honors or '',
        }
        es_list = sorted((es for es in project.energy_saving if es is not None),
                         key=lambda es: es.statistical_year or 0, reverse=True)
        _ch3_imgs = []
        if es_list:
            es_secs = _energy_saving_chapter3_sections(es_list[0], b.unit_short or b.unit_name)
            for k, v in es_secs.items():
                # 3.2 若已从制度文件提炼到正文（management_policy），不再叠加兜底文案
                if k == 'section_3_2' and chapter3.get('section_3_2'):
                    continue
                chapter3[k] = '\n\n'.join(filter(None, [chapter3.get(k, ''), v]))
            # 管理文件 / 获奖证书附件图片（file_resolver 已下载到本地）
            for _p in (es_list[0].management_file_images + es_list[0].award_certificate_images):
                if _p and os.path.exists(_p):
                    _ch3_imgs.append({'path': _p, 'caption': f'图3-{len(_ch3_imgs)+1}'})
        # 第3章照片：合并数据模型分类图片（管理文件/荣誉）
        _ch3_imgs += _chapter_imgs('管理文件/荣誉', prefix='图3')
        if _ch3_imgs:
            chapter3['images'] = _ch3_imgs

        rd = {
            'tags': {
                'audit_type': b.unit_type or '公共机构',
                'institution_category': b.institution_category or '',
                'specific_type': b.specific_type or '',
            },
            'cover': {
                'title': f"{b.unit_name}能源审计报告",
                'audit_organization': b.auditor or '同方德诚（山东）科技股份公司',
                'report_date': b.report_date or datetime.now().strftime('%Y年%m月'),
            },
            'audit_info_tables': {
                # 能源审计机构信息表：机构名称/详细地址来自 ts_register_info（采集进 base），
                # 负责人/联系方式由用户提问提供（base.audit_org_contact/audit_org_phone）；
                # 表内 contact/mobile 仅作预填参考。缺失时保留空串，由 V1/V3 校验拦截提示。
                'institution': {
                    'name': b.audit_org_name or b.auditor,
                    'address': b.audit_org_address,
                    'contact': b.audit_org_contact,
                    'phone': b.audit_org_phone,
                },
                'team_members': [
                    {'role': m.role, 'name': m.name, 'education': m.education,
                     'certification': m.certification, 'major': m.major}
                    for m in project.audit_team
                ],
                'cooperation': [
                    {'role': c.role, 'dept': c.dept, 'name': c.name,
                     'gender': c.gender, 'position': c.position}
                    for c in project.cooperation
                ],
            },
            'chapter1': {
                'audited_unit_short': b.unit_short or b.unit_name,
                'address': b.address,
                'buildings': f"{len(project.buildings)}栋建筑",
                'audit_time': f"{b.audit_start}—{b.audit_end}" if b.audit_start and b.audit_end else '',
                'audit_period': b.audit_period or '',
                'base_period': b.base_period or '',
                'energy_types': [],
                'province': b.province or '山东',
            },
            'chapter2': {
                'unit_name': b.unit_name,
                # 2.1 直接取项目数据 basic_situation（数据收集阶段已从 ts_customer_info 解析，
                # 溯源 PG → Excel → Config）；为空则兜底查询 PG get_customer_info
                'section_2_1': b.basic_situation or self._query_basic_situation_fallback(b.unit_name),
                'building_area': b.building_area,
                'people_count': b.people_count,
                'beds_count': b.beds_count,
                'buildings': [{'name':bg.name or f'建筑{i+1}', 'address':bg.address or b.address,
                               'year':bg.year, 'function':bg.function, 'floors':bg.floors,
                               'area':bg.area, 'use_area':bg.use_area, 'structure':bg.structure,
                               'wall_body_material':bg.wall_body_material,
                               'window_type':bg.window_type, 'insulation':bg.insulation,
                               'roof_insulation':bg.roof_insulation,
                               'roof_insulation_material':bg.roof_insulation_material,
                               'sunshade_type':bg.sunshade_type, 'sunshade_material':bg.sunshade_material,
                               'orientation':bg.orientation, 'function_zoning':bg.function_zoning,
                               'height':bg.height,
                               'cooling_source':bg.cooling_source, 'heating_source':bg.heating_source,
                               'cooling_area':bg.cooling_area, 'heating_area':bg.heating_area,
                               'cooling_terminal':bg.cooling_terminal, 'heating_terminal':bg.heating_terminal,
                               'water_system':bg.water_system, 'fire_system':bg.fire_system,
                               'hot_water':bg.hot_water, 'monitoring':bg.monitoring,
                               'run_time':bg.run_time, 'storey_metrology':bg.storey_metrology,
                               'garage':bg.garage, 'garage_area':bg.garage_area}
                              for i, bg in enumerate(project.buildings)],
                # 建筑照片：分类（建筑外观/各建筑外观）+ 未分类兜底
                'images': _chapter_imgs('建筑外观', '各建筑外观', '', prefix='图2'),
            },
            'chapter3': chapter3,
            'chapter4': {
                'images': _chapter_imgs('计量器具', prefix='图4'),
                'section_4_1': f"计量体系按GB/T29149-2012划分为三级计量。⚠️ 请说明具体计量分级和监测系统建设情况。" if not project.metering.has_monitoring_system else f"计量体系按GB/T29149-2012划分为三级计量。",
                'section_4_2': f"电表{project.metering.electric_meters}块、水表{project.metering.water_meters}块。⚠️ 请确认具体数量和型号。" if not project.metering.electric_meters else f"电表{project.metering.electric_meters}块、水表{project.metering.water_meters}块、气表{project.metering.gas_meters}块。",
                'section_4_3': '⚠️ 请提供数据采集方式和统计制度说明。来源：被审计单位调研表。',
                'section_4_4': '⚠️ 请提供统计工作的成效和存在的问题。来源：现场调研和用户访谈。',
            },
            'chapter5': {
                'text': '',
            },
            'chapter6': {},
            'chapter7': {'images': _chapter_imgs('节能改造示意', prefix='图7')},
            'chapter8': {},
            'sections': {},
        }

        # 能耗数据 → chapter5（结构化，走 indicators 自动计算）
        if hasattr(project, 'energy_yearly') and project.energy_yearly:
            energy_data_list = []
            for ey in project.energy_yearly:
                energy_data_list.append({
                    'year': ey.year,
                    'electricity_kwh': ey.electricity_kwh,
                    'water_m3': ey.water_m3,
                    'natural_gas_m3': ey.natural_gas_m3,
                    'heating_energy_heat_gj': ey.heating_energy_heat_gj,
                    'petrol_kg': ey.petrol_kg,
                    'diesel_kg': ey.diesel_kg,
                    'electricity_cost_wan': ey.electricity_cost_wan,
                    'water_cost_wan': ey.water_cost_wan,
                    'heating_cost_wan': ey.heating_cost_wan,
                    'monthly_electricity_kwh': ey.monthly_electricity_kwh,
                    'monthly_water_m3': ey.monthly_water_m3,
                    'monthly_natural_gas_m3': ey.monthly_natural_gas_m3,
                })
            institution_type = 'medical' if '医疗' in (b.institution_category or '') else ('government' if '党政' in (b.institution_category or '') else 'education')
            # 统一使用 indicators 的机构类型映射
            from tools.energy_audit.indicators import institution_category_to_type
            institution_type = institution_category_to_type(b.institution_category)
            rd['chapter5'] = {
                'energy_data': energy_data_list,
                'unit_name': b.unit_short or b.unit_name,
                'building_area': b.building_area,
                'people_count': b.people_count,
                'beds_count': b.beds_count,
                'institution_type': institution_type,
            }
            # 优先使用 project.indicators（数据提取后已预计算）
            if getattr(project, 'indicators', None) and project.indicators.get('status') == 'ok':
                rd['chapter5']['indicators'] = project.indicators
            else:
                # 兜底：现场计算一次
                try:
                    from tools.energy_audit.indicators import compute_project_indicators
                    rd['chapter5']['indicators'] = compute_project_indicators(project)
                except Exception as e:
                    import logging as _logging
                    _logging.getLogger(__name__).warning(f"load_from_project 兜底计算指标失败: {e}")
            # 自动识别的能源类型同步到 chapter1
            counts = {}
            for d in energy_data_list:
                for k in ['electricity_kwh','water_m3','natural_gas_m3','petrol_kg','diesel_kg']:
                    if d.get(k, 0) and float(d.get(k, 0) or 0) > 0:
                        counts[k] = counts.get(k, 0) + 1
            energy_types = [k for k, v in counts.items() if v > 0]
            rd['chapter1']['energy_types'] = energy_types  # 供 chapter1 使用

        # 第5章账单照片（分类：能耗账单）
        rd['chapter5']['images'] = _chapter_imgs('能耗账单', prefix='图5')

        # 设备 → chapter6
        if project.equipment:
            eq_list = [{'name':eq.name,'category':eq.category,'spec':eq.spec,
                        'quantity':eq.quantity,'remark':eq.remark,
                        'independent_metering':eq.independent_metering,
                        'independent_metering_desc':eq.independent_metering_desc}
                       for eq in project.equipment]
            rd['chapter6'] = ch6 = rd.get('chapter6', {}) or {}
            ch6['_equipment'] = eq_list
            # 第6章设备照片：按系统分组；兼容旧版顶层 images_equipment 消费方（顺序: 制冷→照明→变配电→水泵→厨房）
            _eq_imgs = _chapter_imgs('制冷设备', '照明设备', '变压器/配电', '水泵/水箱', '厨房设备', prefix='图6')
            if _eq_imgs:
                rd['images_equipment'] = [_i['path'] for _i in _eq_imgs]
                ch6['images'] = {
                    'cooling': _chapter_imgs('制冷设备', prefix='图6'),
                    'lighting': _chapter_imgs('照明设备', prefix='图6'),
                    'transformer': _chapter_imgs('变压器/配电', prefix='图6'),
                    'water': _chapter_imgs('水泵/水箱', prefix='图6'),
                    'other_energy': _chapter_imgs('厨房设备', prefix='图6'),
                }

        self.set_report_data(rd)
        return rd

    def generate_word(self, output_path: str) -> str:
        """生成符合格式规范的 Word (.docx) 报告（仅仿写模式）。

        8 章正文硬编码生成已退役（2026-09-04）：默认路径为 author 按
        ea-authoring 技能 LLM 逐章写作 + office_editor 组装，本脚本不写正文。
        """
        return self.word_builder.generate(output_path)

    def generate(self, output_path: str) -> str:
        """仅支持 .docx（仿写模式）"""
        return self.generate_word(output_path)


# ============================================================
# 使用示例
# ============================================================



def _energy_saving_chapter3_sections(es, unit: str) -> dict:
    """从一条节能管理信息（ts_institution_energy_saving）生成第3章各节真实文案。

    返回 {section_3_2 / section_3_3 / section_3_4: 文本}，无对应数据的键不返回；
    load_from_project 会与 management 文案合并，无记录时保留既有兜底文案。
    """
    sections = {}

    # 3.2 能源管理制度
    if es.energy_management == 1:
        sections['section_3_2'] = (f"{unit}已建立能源管理制度，将节能管理纳入日常运营，"
                                   "通过制度建设、定期监督等方式落实节能责任。")
    elif es.energy_management == 0:
        sections['section_3_2'] = f"{unit}目前尚未建立完善的能源管理制度，节能管理仍有提升空间。"

    # 3.3 管理问题与成效
    parts_33 = []
    if es.has_awards == 1 and es.award_name:
        parts_33.append(f"{unit}节能工作取得成效，{es.award_name}。")
    if es.energy_pain_points:
        parts_33.append(f"目前能源利用方面存在的主要痛点：{es.energy_pain_points}。")
    if parts_33:
        sections['section_3_3'] = '\n'.join(parts_33)

    # 3.4 节能改造与管理措施
    parts_34 = []
    replaced = []
    if es.lighting_replacement == 1:
        replaced.append('照明灯具')
    if es.ac_replacement == 1:
        replaced.append('空调设备')
    if es.water_saving_fixture_replacement == 1:
        replaced.append('节水型卫生器具')
    if replaced:
        parts_34.append(f"{unit}已实施{'、'.join(replaced)}更换等节能改造措施。")
    if es.central_ac_control == 1:
        parts_34.append("中央空调系统已增加集中控制，以提升运行能效。")
    if es.other_measures:
        parts_34.append(f"其他节能改造措施：{es.other_measures}。")
    if es.third_party_system:
        parts_34.append(f"能源系统已由第三方托管运营：{es.third_party_system}。")
    if es.charging_pile == 1:
        cp = "单位已配置充电桩"
        if es.charging_settlement:
            cp += f"，结算方式为{es.charging_settlement}"
        if es.charging_installation:
            cp += f"，安装方式为{es.charging_installation}"
        parts_34.append(cp + "。")
    if es.third_party_outsource == 1:
        out = "用能系统已由第三方外包管理"
        if es.outsource_content:
            out += f"，内容包括{es.outsource_content}"
        if es.outsource_settlement:
            out += f"，结算方式为{es.outsource_settlement}"
        parts_34.append(out + "。")
    if parts_34:
        sections['section_3_4'] = '\n'.join(parts_34)

    return sections


def _iso_to_cn(date_str: str) -> str:
    """2022-01-01 → 2022年1月1日"""
    if not date_str or '年' in date_str:
        return date_str
    parts = date_str.split('-')
    if len(parts) >= 3:
        y, m, d = parts[0], str(int(parts[1])), str(int(parts[2]))
        return f"{y}年{m}月{d}日"
    return date_str


def _generate_single_energy_chart(yd_objects, et_key, label, unit, output_dir='./charts'):
    """生成单种能源的逐年柱状图"""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        setup_chart_font(plt)
        years = [yd.year for yd in yd_objects]
        values = [float(getattr(yd, et_key, 0) or 0) for yd in yd_objects]
        if not any(v > 0 for v in values):
            return None
        fig, ax = plt.subplots(figsize=(5, 3))
        bars = ax.bar([str(y) for y in years], values, color='#4CAF50', width=0.4)
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(values)*0.02,
                    f'{val:,.0f}', ha='center', va='bottom', fontsize=8)
        ax.set_ylabel(chart_text(f'{label}({unit})'), fontsize=9)
        ax.set_title(chart_text(f'逐年{label}趋势'), fontsize=11)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        plt.tight_layout()
        os.makedirs(output_dir, exist_ok=True)
        path = os.path.join(output_dir, f'chart_{et_key}.png')
        fig.savefig(path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        return path
    except Exception:
        return None

def _generate_monthly_bar_chart(energy_data_list, et_key, monthly_attr, label, unit, output_dir='./charts'):
    """生成逐月柱状图（年度对比）"""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        setup_chart_font(plt)

        months = ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月']
        fig, ax = plt.subplots(figsize=(10, 5))
        has_data = False
        years_data = []

        for d in energy_data_list:
            monthly = d.get(monthly_attr)
            if monthly and isinstance(monthly, list) and len(monthly) == 12:
                values = [float(v or 0) for v in monthly]
                years_data.append((d.get('year', '?'), values))
                has_data = True

        if not has_data:
            return None

        n_years = len(years_data)
        bar_width = 0.25
        x = range(len(months))
        colors = ['#4CAF50', '#2196F3', '#FF9800']

        for i, (year_label, values) in enumerate(years_data):
            offset = (i - (n_years - 1) / 2) * bar_width
            bars = ax.bar([j + offset for j in x], values, bar_width,
                          label=f'{year_label}年', color=colors[i % 3], edgecolor='white')

        ax.set_xticks(x)
        ax.set_xticklabels(months, fontsize=8)
        ax.set_ylabel(chart_text(f'{label}({unit})'), fontsize=9)
        ax.set_title(chart_text(f'逐月{label}趋势（年度对比）'), fontsize=12, fontweight='bold')
        ax.legend(fontsize=9)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        plt.tight_layout()
        os.makedirs(output_dir, exist_ok=True)
        path = os.path.join(output_dir, f'chart_{et_key}_monthly.png')
        fig.savefig(path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        return path
    except Exception:
        return None

def _generate_cost_pie_chart(year: int, labels: list, values: list, output_dir='./charts'):
    """生成单年能源费用占比饼状图"""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        setup_chart_font(plt)

        # 过滤0值
        filtered = [(l, v) for l, v in zip(labels, values) if v > 0]
        if not filtered:
            return None
        lbls, vals = zip(*filtered)

        fig, ax = plt.subplots(figsize=(5, 4))
        colors = ['#4CAF50','#2196F3','#FF9800','#F44336','#9C27B0']
        wedges, texts, autotexts = ax.pie(
            vals, labels=lbls, autopct='%1.1f%%',
            colors=colors[:len(vals)], startangle=90,
            textprops={'fontsize': 9}
        )
        ax.set_title(chart_text(f'{year}年能源费用占比'), fontsize=12)

        plt.tight_layout()
        os.makedirs(output_dir, exist_ok=True)
        path = os.path.join(output_dir, f'cost_pie_{year}.png')
        fig.savefig(path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        return path
    except Exception:
        return None


if __name__ == "__main__":
    sample_data = {
        'cover': {
            'title': '山东省某政府机关能源审计报告',
            'audit_organization': '同方德诚科技有限公司',
            'report_date': '2026年6月',
        },
        'audit_info_tables': {
            'institution': {'name': '测试单位', 'address': '测试路1号', 'contact': '张三', 'phone': '13800000000'},
            'team_members': [{'role':'组长','name':'李四','education':'硕士','certification':'工程师','major':'暖通'}],
            'cooperation': [{'role':'配合','dept':'办公室','name':'王五','gender':'男','position':'主任'}],
        },
        'chapter1': {'audited_unit_short': '测试单位', 'audit_time': '2025年6月—2025年7月', 'audit_period': '2022年1月-2024年12月', 'base_period': '2021年1月-2023年12月', 'energy_types': ['electricity_kwh','water_m3'], 'province': '山东'},
        'chapter2': {'unit_name': '测试单位', 'building_area': 5000, 'people_count': 200, 'buildings': [{'name':'主楼','year':2020,'floors':'5层','structure':'框架'}]},
        'chapter5': {'energy_data': [{'year':2022,'electricity_kwh':500000,'water_m3':5000,'natural_gas_m3':3000},{'year':2023,'electricity_kwh':520000,'water_m3':5500,'natural_gas_m3':3200}], 'building_area': 5000, 'people_count': 200},
        'chapter6': {'_equipment': [{'name':'中央空调','category':'空调','spec':'30kW','quantity':3}]},
        'sections': {
            '1.1': '为贯彻落实《公共机构节能条例》，评估该单位能源使用状况，发现节能潜力。',
        }
    }

    gen = ReportGenerator("公共机构")
    gen.set_report_data(sample_data)

    # 生成 Word
    gen.generate_word("能源审计报告.docx")
    print("✓ Word报告已生成: 能源审计报告.docx")

    # 生成 Markdown
    md = gen.generate_markdown("能源审计报告.md")
    print(f"✓ Markdown报告已生成: 能源审计报告.md ({len(md)} 字符)")
