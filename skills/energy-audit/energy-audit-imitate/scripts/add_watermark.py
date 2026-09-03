#!/usr/bin/env python3
"""Inject a DrawingML unit-name watermark into every section header.

OnlyOffice-compatible: header DrawingML with behindDoc=1. Never VML textpath.

Usage:
  python scripts/add_watermark.py report.docx "烟台经济技术开发区人民法院"
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path


def _watermark_paragraph_xml(text: str, doc_pr_id: int) -> str:
    safe = html.escape(text, quote=True)
    size = "88" if len(text) <= 12 else "56"
    return f'''
<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
     xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
     xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
     xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape">
  <w:r>
    <w:drawing>
      <wp:anchor distT="0" distB="0" distL="0" distR="0" simplePos="0"
                 relativeHeight="251658240" behindDoc="1" locked="0"
                 layoutInCell="1" allowOverlap="1">
        <wp:simplePos x="0" y="0"/>
        <wp:positionH relativeFrom="page"><wp:align>center</wp:align></wp:positionH>
        <wp:positionV relativeFrom="page"><wp:align>center</wp:align></wp:positionV>
        <wp:extent cx="5486400" cy="2194560"/>
        <wp:effectExtent l="0" t="0" r="0" b="0"/>
        <wp:wrapNone/>
        <wp:docPr id="{doc_pr_id}" name="EAWatermark"/>
        <wp:cNvGraphicFramePr>
          <a:graphicFrameLocks xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" noChangeAspect="1"/>
        </wp:cNvGraphicFramePr>
        <a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
          <a:graphicData uri="http://schemas.microsoft.com/office/word/2010/wordprocessingShape">
            <wps:wsp>
              <wps:cNvSpPr txBox="1"/>
              <wps:spPr>
                <a:xfrm rot="2700000">
                  <a:off x="0" y="0"/>
                  <a:ext cx="5486400" cy="2194560"/>
                </a:xfrm>
                <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
                <a:noFill/>
                <a:ln><a:noFill/></a:ln>
              </wps:spPr>
              <wps:txbx>
                <w:txbxContent>
                  <w:p>
                    <w:pPr><w:jc w:val="center"/></w:pPr>
                    <w:r>
                      <w:rPr>
                        <w:rFonts w:ascii="宋体" w:eastAsia="宋体" w:hAnsi="宋体"/>
                        <w:sz w:val="{size}"/>
                        <w:szCs w:val="{size}"/>
                        <w:color w:val="C0C0C0"/>
                      </w:rPr>
                      <w:t>{safe}</w:t>
                    </w:r>
                  </w:p>
                </w:txbxContent>
              </wps:txbx>
              <wps:bodyPr wrap="none" fromWordArt="0"><a:noAutofit/></wps:bodyPr>
            </wps:wsp>
          </a:graphicData>
        </a:graphic>
      </wp:anchor>
    </w:drawing>
  </w:r>
</w:p>'''


def add_unit_name_watermark(docx_path: str, unit_name: str) -> None:
    """Write a DrawingML watermark named EAWatermark into each section header."""
    name = (unit_name or "").strip()
    if not name:
        raise ValueError("水印文案为空：需要被审计单位全称 unit_name")
    from docx import Document
    from docx.oxml import parse_xml

    path = Path(docx_path)
    doc = Document(str(path))
    n = 1
    for section in doc.sections:
        headers = [section.header]
        if section.different_first_page_header_footer:
            headers.append(section.first_page_header)
        if getattr(section, "even_page_header", None) is not None:
            headers.append(section.even_page_header)
        for header in headers:
            xml = header._element.xml
            if "v:textpath" in xml:
                raise RuntimeError("页眉含 VML textpath，禁止交付；改为 DrawingML 后重试")
            if "EAWatermark" in xml or 'name="Watermark"' in xml:
                continue
            header._element.append(parse_xml(_watermark_paragraph_xml(name, n)))
            n += 1
    doc.save(str(path))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Add DrawingML unit-name watermark to a .docx")
    parser.add_argument("docx", help="Path to the assembled report")
    parser.add_argument("unit_name", help="Audited unit full name (watermark text)")
    args = parser.parse_args(argv)
    path = Path(args.docx)
    if not path.is_file():
        print(f"docx not found: {path}", file=sys.stderr)
        return 2
    try:
        add_unit_name_watermark(str(path), args.unit_name)
    except Exception as exc:
        print(f"watermark failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "file_path": str(path), "watermark": args.unit_name.strip()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
