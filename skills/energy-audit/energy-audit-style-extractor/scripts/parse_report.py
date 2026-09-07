#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""样板报告结构化解析器：docx/md → 按标题层级分块的结构化文本。

供 energy-audit-style-extractor 的"三遍提取"使用。
不解读内容、不改写文字，只做结构还原：
- docx：按 Heading 1/2/3 样式（或 outlineLvl）识别层级；正文段落、表格原样保留
- md：原样透传（已含标题/表格语法）

用法:
    python parse_report.py <report.docx|report.md> [--out parsed.txt]

输出约定（与提取 schema 对接）：
    # 第X章 章名          → 章
    ## X.Y 节名           → 节
    ### X.Y.Z 小节名      → 小节
    表格行以 | ... | 保留
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")


def parse_md(text: str) -> str:
    """markdown 原样透传（本身已是结构化文本）。"""
    return text.strip()


def _style_level(style_name: str) -> int:
    """把 Word 样式名映射到标题层级；非标题返回 0。"""
    s = (style_name or "").strip().lower()
    m = re.match(r"^(?:heading|标题)\s*(\d)", s)
    if m:
        return int(m.group(1))
    if s in ("heading", "标题"):
        return 1
    if s in ("title",):
        return 0  # 文档大标题不算章节
    return 0


def parse_docx(path: str) -> str:
    """docx → 结构化 markdown 文本（标题层级 + 正文 + 表格）。"""
    try:
        import docx  # python-docx
    except ImportError:
        print("[parse_report] 缺少 python-docx，请先安装（Hermes energy extra）", file=sys.stderr)
        sys.exit(1)

    document = docx.Document(path)
    lines: list[str] = []
    for block in document.element.body.iterchildren():
        tag = block.tag.split("}")[-1]
        if tag == "p":
            # 用段落对象取文本与样式
            from docx.text.paragraph import Paragraph

            para = Paragraph(block, document)
            style = (para.style.name if para.style is not None else "") or ""
            level = _style_level(style)
            # 无 Heading 样式时尝试 outlineLvl
            if level == 0:
                ppr = block.find(".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}outlineLvl")
                if ppr is not None and ppr.get(
                    "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val"
                ):
                    try:
                        level = int(
                            ppr.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val")
                        ) + 1
                    except (TypeError, ValueError):
                        level = 0
            text = para.text.strip()
            if not text:
                continue
            if level >= 1:
                lines.append(f"{'#' * min(level, 6)} {text}")
            else:
                lines.append(text)
        elif tag == "tbl":
            from docx.table import Table

            table = Table(block, document)
            for row in table.rows:
                cells = [c.text.strip().replace("\n", " ") for c in row.cells]
                lines.append("| " + " | ".join(cells) + " |")
            lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="样板报告结构化解析（docx/md → 分块文本）")
    parser.add_argument("report", help="样板报告路径（.docx 或 .md）")
    parser.add_argument("--out", default="", help="输出文件；缺省打印到 stdout")
    args = parser.parse_args(argv)

    src = Path(args.report)
    if not src.exists():
        print(f"[parse_report] 文件不存在: {src}", file=sys.stderr)
        return 1

    suffix = src.suffix.lower()
    if suffix == ".docx":
        text = parse_docx(str(src))
    elif suffix in (".md", ".markdown", ".txt"):
        text = parse_md(src.read_text(encoding="utf-8", errors="replace"))
    else:
        print("[parse_report] 仅支持 .docx / .md / .txt", file=sys.stderr)
        return 1

    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"[parse_report] 已写出 {args.out}（{len(text)} 字符）")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
