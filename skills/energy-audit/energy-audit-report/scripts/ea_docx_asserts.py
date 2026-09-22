#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ea_docx_asserts.py — 能源审计报告 .docx/.pdf 交付断言器（脚本化装配方案 T0）。

用法:
    python ea_docx_asserts.py <报告.docx> [--pdf <报告.pdf>] [--expect k=v ...] [--json out.json]

硬检查（任一失败 → exit 1）:
    zip_ok            docx 可解包
    toc_field         document.xml 含 TOC 域（instrText 含 'TOC'）
    update_fields     word/settings.xml 含 <w:updateFields>
    header_watermark  前置/正文两节页眉均含 EAWatermark（DrawingML 水印）
    header_divider    正文节页眉含 w:pBdr 底边线；前置节页眉不得含边框
    footer_page       正文节页脚含 PAGE 域
    footer_plain      正文节页脚为纯数字（无「—」或其它文字）
    header_no_vml     页眉无 VML 水印（禁 v:textpath）
    section_split     节数=2（前置节/正文节；2026-09-22 分节）
    prebody_clean     前置节：无页脚引用、页眉无文字、无边框（仅水印）
    body_numbering    正文节含 <w:pgNumType w:start="1"/>（页码从 1 重起）
    toc_no_self_ref   目录未自收录（目录区不重复出现「目录」字样，启发式）
    no_flat_formula   无公式压平残留（已知形态清单）
    no_writer_markers 无写作标记残留（写作参考/数据参考/逐月参考/[FORMULA）
    ch5_narrative     第5章分析叙述段计数 ≥ 15（防「只有图表无文字」，2026-09-20 新增）
    --pdf 时另加 2 项:
    pdf_prebody_clean 正文前页面无页眉文字、无页脚数字
    pdf_footer_seq    正文页脚数字序列连续（从 1 起）

度量（总是输出）: oMath / captions / tables / drawings / media_files / ch5_body_paras
                  building_tables / building_tables_cols（建筑基本信息表数量与各表列数）
                  pages / prebody_pages / header_pages / footer_pages（需 --pdf；后三者=正文口径）
--expect 键: pages（容差 ±2）/ oMath / captions / tables / drawings / media_files
"""
import argparse
import json
import re
import sys
import zipfile

from lxml import etree

MARKERS = ["写作参考", "数据参考", "逐月参考", "[FORMULA"]
FLAT_FORMULAS = ["Ejrcn=E", "Eja=ED", "Er=EP", "Vuc=Vk", "Egnm=Egn"]
IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".emf", ".wmf", ".tif", ".tiff")
W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def visible_text(doc_xml: str) -> str:
    x = re.sub(r"<w:tab[^>]*/>", " ", doc_xml)
    x = re.sub(r"<w:br[^>]*/>", " ", x)
    return "".join(re.findall(r"<w:t(?: [^>]*)?>([^<]*)</w:t>", x))


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s)


def count_captions(doc_xml: str) -> int:
    """图注计数：按段落拼接全部 w:t 后判定（Word 保存会重排 run 分割，
    不能用单 w:t 正则，否则收尾后计数误报 0）。"""
    n = 0
    for m in re.finditer(r"<w:p[ >].*?</w:p>", doc_xml, re.S):
        t = "".join(re.findall(r"<w:t(?: [^>]*)?>([^<]*)</w:t>", m.group(0)))
        if re.match(r"图\d+\.\d+", re.sub(r"\s+", "", t)):
            n += 1
    return n


def ch5_narrative_count(doc_xml: str) -> int:
    """第5章分析叙述段计数（2026-09-20 新增）：剔表格/标题/图注表题后，≥12 字段落数。

    区间 = 正文中最后一次「第5章」标题之后、其后首个「第6章」标题之前
    （目录区条目早于正文标题，天然被排除）。"""
    x = re.sub(r"<w:tbl[ >].*?</w:tbl>", " ", doc_xml, flags=re.S)
    paras = []
    for m in re.finditer(r"<w:p[ >].*?</w:p>", x, re.S):
        t = "".join(re.findall(r"<w:t(?: [^>]*)?>([^<]*)</w:t>", m.group(0)))
        paras.append(re.sub(r"\s+", "", t))
    idx5 = None
    for i, t in enumerate(paras):
        if t.startswith("第5章"):
            idx5 = i
    if idx5 is None:
        return 0
    idx6 = len(paras)
    for j in range(idx5 + 1, len(paras)):
        if paras[j].startswith("第6章"):
            idx6 = j
            break
    n = 0
    for t in paras[idx5 + 1:idx6]:
        if len(t) < 12:
            continue
        if re.match(r"^\d+\.\d+", t):       # 小节标题
            continue
        if re.match(r"^[图表]\s*\d", t):     # 图注/表题
            continue
        n += 1
    return n


def building_tables_info(doc_xml: str):
    """建筑基本信息表检测（2026-09-20 新增）：返回各建筑表「首行列数」列表。

    识别：前 3 行内出现「建筑名称/建筑物名称」（兼容「项目 | 内容」旧表头形态）。
    用途：building_tables / building_tables_cols 度量（结构合规性由 V3 负责 P1 检查）。
    """
    cols = []
    for tm in re.finditer(r"<w:tbl[ >].*?</w:tbl>", doc_xml, flags=re.S):
        tbl = tm.group(0)
        rows = re.findall(r"<w:tr[ >].*?</w:tr>", tbl, flags=re.S)[:3]
        if not rows:
            continue
        n_cols = 0
        hit = False
        for k, tr in enumerate(rows):
            tcs = re.findall(r"<w:tc[ >].*?</w:tc>", tr, flags=re.S)
            if not tcs:
                continue
            if k == 0:
                n_cols = len(tcs)
            first = "".join(re.findall(r"<w:t(?: [^>]*)?>([^<]*)</w:t>", tcs[0]))
            if ("建筑名称" in first) or ("建筑物名称" in first):
                hit = True
        if hit:
            cols.append(n_cols)
    return cols


def section_hf_map(z):
    """按 sectPr 顺序返回每节的页眉/页脚部件名（含 sectPr 原文）。

    映射链：w:headerReference / w:footerReference → r:id → word/_rels/document.xml.rels。
    """
    root = etree.fromstring(z.read("word/document.xml"))
    rid_map = {}
    try:
        rels = etree.fromstring(z.read("word/_rels/document.xml.rels"))
        for rel in rels:
            rid_map[rel.get("Id")] = rel.get("Target")
    except KeyError:
        pass
    out = []
    for sp in root.findall(".//%ssectPr" % W_NS):
        entry = {"header": [], "footer": [], "xml": etree.tostring(sp, encoding="unicode")}
        for tag, key in (("headerReference", "header"), ("footerReference", "footer")):
            for ref in sp.findall("%s%s" % (W_NS, tag)):
                tgt = (rid_map.get(ref.get(R_NS + "id")) or "").lstrip("/")
                if tgt and not tgt.startswith("word/"):
                    tgt = "word/" + tgt
                if tgt:
                    entry[key].append(tgt)
        out.append(entry)
    return out


def run(docx: str, pdf: str = None):
    z = zipfile.ZipFile(docx)
    znames = z.namelist()
    doc = z.read("word/document.xml").decode("utf-8", "ignore")
    settings = z.read("word/settings.xml").decode("utf-8", "ignore") if "word/settings.xml" in znames else ""
    headers = {n: z.read(n).decode("utf-8", "ignore") for n in znames if re.fullmatch(r"word/header\d+\.xml", n)}
    footers = {n: z.read(n).decode("utf-8", "ignore") for n in znames if re.fullmatch(r"word/footer\d+\.xml", n)}
    media = [n for n in znames if n.startswith("word/media/") and n.lower().endswith(IMG_EXT)]
    sec_maps = section_hf_map(z)

    instrs = re.findall(r"<w:instrText[^>]*>([^<]*)</w:instrText>", doc)
    text = visible_text(doc)
    tn = norm(text)
    ch5_n = ch5_narrative_count(doc)
    bldg_cols = building_tables_info(doc)
    i = tn.find("目录")
    self_ref = False
    if i >= 0:
        # 剔除未缓存占位的"（打开文档…）"文本（R7 形态带前置"目录"，构建器形态
        # "目录"在括号内）；仅当剔除后仍出现"目录"时才判为自收录（历史 bug 形态）。
        seg = re.sub(r"(目录)?（打开文档[^）]*）", "", tn[i + 2:i + 900])
        j = seg.find("目录")
        if j >= 0:
            self_ref = True
    toc_state = "placeholder" if "（打开文档" in tn else "cached"
    pre_map = sec_maps[0] if sec_maps else {"header": [], "footer": [], "xml": ""}
    body_map = sec_maps[-1] if sec_maps else {"header": [], "footer": [], "xml": ""}
    pre_hdr = "".join(headers.get(n, "") for n in pre_map["header"])
    body_hdr = "".join(headers.get(n, "") for n in body_map["header"])
    body_ftr = "".join(footers.get(n, "") for n in body_map["footer"])

    checks = {
        "zip_ok": True,
        "toc_field": any("TOC" in s for s in instrs),
        "update_fields": "updateFields" in settings,
        "header_watermark": ("EAWatermark" in pre_hdr) and ("EAWatermark" in body_hdr),
        "header_divider": ("w:pBdr" in body_hdr and "w:bottom" in body_hdr) and ("pBdr" not in pre_hdr),
        "footer_page": "PAGE" in body_ftr,
        "footer_plain": ("PAGE" in body_ftr) and ("—" not in body_ftr),
        "header_no_vml": not any("v:textpath" in h for h in headers.values()),
        "section_split": len(sec_maps) == 2,
        "prebody_clean": (not pre_map["footer"]) and ("能源审计报告" not in pre_hdr) and ("pBdr" not in pre_hdr),
        "body_numbering": ("w:pgNumType" in body_map["xml"]) and ("w:start=\"1\"" in body_map["xml"]),
        "toc_no_self_ref": not self_ref,
        "no_flat_formula": not [p for p in FLAT_FORMULAS if p in text],
        "no_writer_markers": not [m for m in MARKERS if m in text],
        "ch5_narrative": ch5_n >= 15,
    }
    details = {}
    flat = [p for p in FLAT_FORMULAS if p in text]
    marks = [m for m in MARKERS if m in text]
    if flat:
        details["no_flat_formula"] = flat
    if marks:
        details["no_writer_markers"] = marks
    if ch5_n < 15:
        details["ch5_narrative"] = "第5章叙述段仅 %d 段（需 ≥ 15）" % ch5_n
    if not checks["section_split"]:
        details["section_split"] = "sectPr 数=%d（期望 2：前置/正文）" % len(sec_maps)
    if not checks["prebody_clean"]:
        why = []
        if pre_map["footer"]:
            why.append("前置节含页脚引用 %s" % pre_map["footer"])
        if "能源审计报告" in pre_hdr:
            why.append("前置节页眉含文字")
        if "pBdr" in pre_hdr:
            why.append("前置节页眉含边框")
        details["prebody_clean"] = "；".join(why) or "未知"
    if not checks["body_numbering"]:
        details["body_numbering"] = "正文节缺 w:pgNumType start=1"
    if not checks["footer_plain"]:
        details["footer_plain"] = "正文节页脚含破折号或缺失 PAGE 域"

    metrics = {
        "toc_state": toc_state,
        "oMath": len(re.findall(r"<m:oMath(?![A-Za-z])", doc)),
        "captions": count_captions(doc),
        "tables": len(re.findall(r"<w:tbl[ >]", doc)),
        "ch5_body_paras": ch5_n,
        "building_tables": len(bldg_cols),
        "building_tables_cols": ",".join(str(c) for c in bldg_cols) or "-",
        "drawings": len(re.findall(r"<w:drawing[ >]", doc)),
        "media_files": len(media),
    }
    if pdf:
        import fitz
        d = fitz.open(pdf)
        n = d.page_count
        metrics["pages"] = n

        def _bottom_digit(page):
            """页脚带（底部 66pt）唯一行且为纯数字 → 页码；否则 None。"""
            h = page.rect.height
            lines = []
            for b in page.get_text("dict").get("blocks", []):
                for l in b.get("lines", []):
                    txt = "".join(s.get("text", "") for s in l.get("spans", [])).strip()
                    if txt:
                        lines.append((l["bbox"][3], txt))
            cand = [(y1, tx) for y1, tx in lines if y1 >= h - 66]
            if len(cand) == 1 and re.fullmatch(r"\d+", cand[0][1]):
                return int(cand[0][1])
            return None

        def _top_has_header(page):
            band = "".join(w[4] for w in page.get_text("words") if w[1] < 60)
            return "能源审计报告" in re.sub(r"\s+", "", band)

        nums = [_bottom_digit(d[j]) for j in range(n)]
        tops = [_top_has_header(d[j]) for j in range(n)]
        first = next((j for j in range(n) if nums[j] == 1), None)
        if first is None:
            checks["pdf_footer_from_1"] = False
            details["pdf_footer_from_1"] = "未找到页脚为「1」的正文首页（页码从 1 未生效？）"
            metrics["prebody_pages"] = "-"
            metrics["header_pages"] = "-"
            metrics["footer_pages"] = "-"
        else:
            metrics["prebody_pages"] = first
            pre_bad = []
            for j in range(first):
                if tops[j]:
                    pre_bad.append("p%d 顶部带页眉文字" % (j + 1))
                if nums[j] is not None:
                    pre_bad.append("p%d 含页脚数字 %s" % (j + 1, nums[j]))
            checks["pdf_prebody_clean"] = not pre_bad
            if pre_bad:
                details["pdf_prebody_clean"] = "；".join(pre_bad[:6])
            body_pages = n - first
            hf = sum(1 for j in range(first, n) if tops[j])
            ff = sum(1 for j in range(first, n) if nums[j] == j - first + 1)
            metrics["header_pages"] = "%d/%d" % (hf, body_pages)
            metrics["footer_pages"] = "%d/%d" % (ff, body_pages)
            checks["pdf_footer_seq"] = (ff == body_pages)
            if ff != body_pages:
                bad = [("p%d" % (j + 1), nums[j]) for j in range(first, n)
                       if nums[j] != j - first + 1][:6]
                details["pdf_footer_seq"] = "断点: %s" % bad
    return checks, metrics, details


def main() -> int:
    ap = argparse.ArgumentParser(description="能源审计报告交付断言器")
    ap.add_argument("docx")
    ap.add_argument("--pdf", default=None)
    ap.add_argument("--expect", action="append", default=[], help="k=v，可重复；pages 容差 ±2")
    ap.add_argument("--json", dest="json_out", default=None)
    args = ap.parse_args()

    try:
        checks, metrics, details = run(args.docx, args.pdf)
    except Exception as exc:  # 解包失败等
        print("[FAIL] zip_ok — %s" % exc)
        if args.json_out:
            json.dump({"docx": args.docx, "passed": False, "error": str(exc)},
                      open(args.json_out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        return 1

    exp_fail = []
    for e in args.expect:
        k, _, v = e.partition("=")
        k, v = k.strip(), v.strip()
        got = metrics.get(k)
        if got is None:
            exp_fail.append("%s: 无度量值（需要 --pdf？）" % k)
            continue
        try:
            if k == "pages":
                ok = abs(int(got) - int(v)) <= 2
            else:
                ok = int(got) == int(v)
        except (TypeError, ValueError):
            ok = False
        if not ok:
            exp_fail.append("%s: got %s expect %s" % (k, got, v))

    failed = [k for k, v in checks.items() if not v] + ["expect:" + f for f in exp_fail]

    for k, v in checks.items():
        tag = "[OK]" if v else "[FAIL]"
        d = ""
        if k in details:
            d = " — %s" % details[k]
        print("%s %s%s" % (tag, k, d))
    for f in exp_fail:
        print("[FAIL] expect %s" % f)
    print("-- metrics --")
    for k, v in metrics.items():
        print("  %s = %s" % (k, v))

    if args.json_out:
        json.dump({
            "docx": args.docx, "pdf": args.pdf,
            "checks": checks, "details": details, "metrics": metrics,
            "failed": failed, "passed": not failed,
        }, open(args.json_out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    print("[%s] %d 检查失败" % ("PASS" if not failed else "FAIL", len(failed)))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
