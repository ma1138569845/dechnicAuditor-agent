#!/usr/bin/env python3
"""fix_header_footer.py — 能源审计报告页眉文字+分隔线、页脚纯 PAGE 域一键注入。

背景：assemble / ReportGenerator / add_watermark.py 均不生成页眉文字
（word-finishing.md §3/§4），本脚本在装配完成后用 zip + lxml 直接注入
header*.xml / footer*.xml。只动 default 页眉/页脚（封面节页眉空白不动、
evenAndOddHeaders 默认关闭不处理 even）。

用法：
    python fix_header_footer.py <报告.docx> <被审计单位全称> [--dry-run]

规范（docx-ooxml-techniques.md 页眉小节 + word-finishing.md §3/§4）：
    - 页眉：单位全称 + 两空格 + "能源审计报告"，右对齐，宋体 10.5pt（sz=21），
      黑色不加粗，下方分隔线 w:pBdr/w:bottom(single, sz=6, 000000)。
    - 页脚：仅 PAGE 域数字，居中，10.5pt（sz=21），Times New Roman + eastAsia 宋体。
"""
import argparse
import re
import sys
import zipfile

from lxml import etree

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _q(tag: str) -> str:
    return "{%s}%s" % (W_NS, tag)


def _pxml(s):
    if isinstance(s, str):
        s = s.encode("utf-8")
    return etree.fromstring(s)


# 页眉文字段落 XML（右对齐 + 底边线 + 宋体 10.5pt）
def _header_paragraph_xml(unit_name: str) -> str:
    return (
        '<w:p xmlns:w="%s">'
        "<w:pPr>"
        '<w:jc w:val="right"/>'
        '<w:pBdr><w:bottom w:val="single" w:color="000000" w:sz="6"/></w:pBdr>'
        "<w:rPr>"
        '<w:rFonts w:ascii="Times New Roman" w:eastAsia="宋体" w:hAnsi="Times New Roman"/>'
        '<w:sz w:val="21"/><w:szCs w:val="21"/>'
        "</w:rPr>"
        "</w:pPr>"
        "<w:r>"
        "<w:rPr>"
        '<w:rFonts w:ascii="Times New Roman" w:eastAsia="宋体" w:hAnsi="Times New Roman"/>'
        '<w:sz w:val="21"/><w:szCs w:val="21"/>'
        "</w:rPr>"
        '<w:t xml:space="preserve">%s  能源审计报告</w:t>'
        "</w:r>"
        "</w:p>" % (W_NS, unit_name)
    )


# 页脚 PAGE 域段落 XML（居中 + 10.5pt）
_FOOTER_PAGE_XML = (
    '<w:p xmlns:w="%s">'
    "<w:pPr>"
    '<w:jc w:val="center"/>'
    "<w:rPr>"
    '<w:rFonts w:ascii="Times New Roman" w:eastAsia="宋体" w:hAnsi="Times New Roman"/>'
    '<w:sz w:val="21"/><w:szCs w:val="21"/>'
    "</w:rPr>"
    "</w:pPr>"
    "<w:r><w:fldChar w:fldCharType=\"begin\"/></w:r>"
    "<w:r><w:instrText xml:space=\"preserve\"> PAGE </w:instrText></w:r>"
    "<w:r><w:fldChar w:fldCharType=\"separate\"/></w:r>"
    "<w:r><w:t>1</w:t></w:r>"
    "<w:r><w:fldChar w:fldCharType=\"end\"/></w:r>"
    "</w:p>" % W_NS
)


def _default_header_targets(document_xml: str, rels_xml: str):
    """返回 (sectPr 顺序, headerN.xml 名) 列表，仅 type=default。"""
    root = _pxml(document_xml)
    sect_prs = root.iter(_q("sectPr"))
    # 节序：document.xml 正文里最后一个 sectPr 是最后一节的；其余是每节末尾。
    # 这里只关心哪些 header 文件是 default（封面节引用 first，天然被排除）。
    R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    targets = set()
    for sect in sect_prs:
        for ref in sect.findall(_q("headerReference")):
            if ref.get(_q("type")) == "default":
                r_id = ref.get("{%s}id" % R_NS)
                if r_id:
                    targets.add(r_id)
    rels_root = _pxml(rels_xml)
    header_files = []
    for rel in rels_root:
        if rel.get("Type", "").endswith("/header") and rel.get("Id") in targets:
            target = rel.get("Target")
            if target:
                header_files.append("word/" + target.lstrip("/"))
    return header_files


def _fix_header(xml: str, unit_name: str) -> str:
    """页眉：保留 DrawingML 水印段落，其余段落清空重写为规范单段落。"""
    root = _pxml(xml)
    body = root
    paras = [p for p in body.iter(_q("p"))]
    new_p = _pxml(_header_paragraph_xml(unit_name))
    inserted = False
    for p in paras:
        has_drawing = p.find(".//" + _q("drawing")) is not None
        if has_drawing:
            continue  # 水印段落保留
        if not inserted:
            p_parent = p.getparent()
            p_parent.replace(p, new_p)
            inserted = True
        else:
            p_parent = p.getparent()
            p_parent.remove(p)
    if not inserted:
        body.append(new_p)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True).decode("utf-8")


def _fix_footer(xml: str) -> str:
    """页脚：清空全部段落，写纯 PAGE 域居中段落。"""
    root = _pxml(xml)
    for p in list(root.iter(_q("p"))):
        p.getparent().remove(p)
    root.append(_pxml(_FOOTER_PAGE_XML))
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True).decode("utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="页眉文字+分隔线、页脚纯 PAGE 域注入")
    ap.add_argument("docx", help="报告 .docx 路径")
    ap.add_argument("unit_name", help="被审计单位全称")
    ap.add_argument("--dry-run", action="store_true", help="只打印将修改的文件，不写盘")
    args = ap.parse_args()

    zin = zipfile.ZipFile(args.docx)
    try:
        document_xml = zin.read("word/document.xml").decode("utf-8")
        rels_xml = zin.read("word/_rels/document.xml.rels").decode("utf-8")
    except KeyError as exc:
        print("缺文件: %s（不是标准 docx？）" % exc, file=sys.stderr)
        return 1

    header_files = _default_header_targets(document_xml, rels_xml)
    footer_files = [
        n for n in zin.namelist()
        if re.match(r"^word/footer\d*\.xml$", n)
    ]
    print("页眉（default）目标: %s" % header_files)
    print("页脚目标: %s" % footer_files)
    if args.dry_run:
        return 0

    new_entries = {}
    for name in header_files:
        xml = zin.read(name).decode("utf-8")
        new_entries[name] = _fix_header(xml, args.unit_name)
    for name in footer_files:
        xml = zin.read(name).decode("utf-8")
        new_entries[name] = _fix_footer(xml)
    zin.close()

    # 重建 zip（保留未改 entry 原字节）
    tmp = args.docx + ".tmp"
    with zipfile.ZipFile(args.docx) as src, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = new_entries.get(item.filename, None)
            dst.writestr(item, data if data is not None else src.read(item.filename))
    import os
    os.replace(tmp, args.docx)
    print("已注入 %d 个页眉 / %d 个页脚" % (len(header_files), len(footer_files)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
