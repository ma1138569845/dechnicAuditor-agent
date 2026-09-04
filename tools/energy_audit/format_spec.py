"""格式规范权威单点（2026-09-04 从 report_generator.py 提取）。

报告 Word 排版规范常量（字体/字号/对齐/行距/表格行高），
author 写作与 datava 格式校验均以本文件为准，禁止在多处复制数值。
"""

from dataclasses import dataclass, field

@dataclass
class FormatSpec:
    """Word 格式规范（基于19份省直报告统计）"""
    # 正文字体
    body_font_cn: str = "宋体"
    body_font_en: str = "Times New Roman"
    body_size: int = 12  # pt（小四号）
    body_line_spacing: float = 1.5
    body_first_line_indent: float = 2.0  # 字符
    body_alignment: int = 3  # 3=两端对齐(JUSTIFY)

    # 一级标题（第X章）— 小三号(15pt) 宋体 居中
    h1_font: str = "宋体"
    h1_size: int = 15  # 小三号
    h1_bold: bool = True
    h1_alignment: int = 1  # 1=居中
    h1_line_spacing: float = 1.5
    h1_space_before: int = 24
    h1_space_after: int = 12

    # 二级标题（X.X）— 四号(14pt) 宋体
    h2_font: str = "宋体"
    h2_size: int = 14  # 四号
    h2_bold: bool = True
    h2_alignment: int = 0  # 左对齐
    h2_line_spacing: float = 1.5
    h2_space_before: int = 12
    h2_space_after: int = 6

    # 三级标题（X.X.X）
    h3_font: str = "宋体"
    h3_size: int = 12
    h3_bold: bool = True
    h3_alignment: int = 0
    h3_line_spacing: float = 1.5

    # 封面
    cover_title_size: int = 36  # 被审计单位名称 + "能源审计报告"
    cover_info_size: int = 14   # 审计机构 + 日期

    # 表格
    table_header_size: int = 12      # 小四号
    table_content_size: int = 12     # 小四号
    table_line_spacing: float = 1.0

    # 计量单位格式
    unit_separator: str = " "  # 数字 + 空格 + 单位


FMT = FormatSpec()


# ============================================================
# 章节结构定义
# ============================================================

