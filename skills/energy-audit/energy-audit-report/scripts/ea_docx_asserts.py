#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ea_docx_asserts.py — 能源审计报告 .docx/.pdf 交付断言器（脚本化装配方案 T0）。

用法:
    python ea_docx_asserts.py <报告.docx> [--pdf <报告.pdf>] [--expect k=v ...] [--json out.json]

硬检查（任一失败 → exit 1）:
    zip_ok            docx 可解包
    toc_field         document.xml 含 TOC 域（instrText 含 'TOC'）
    update_fields     word/settings.xml 含 <w:updateFields>
    header_watermark  页眉含 EAWatermark（DrawingML 水印）
    header_divider    页眉段落含 w:pBdr 底边线
    footer_page       页脚含 PAGE 域
    header_no_vml     页眉无 VML 水印（禁 v:textpath）
    toc_no_self_ref   目录未自收录（目录区不重复出现"目录"字样，启发式）
    no_flat_formula   无公式压平残留（已知形态清单）
    no_writer_markers 无写作标记残留（写作参考/数据参考/逐月参考/[FORMULA）
    ch5_narrative     第5章分析叙述段计数 ≥ 15（防「只有图表无文字」，2026-09-20 新增）

度量（总是输出）: oMath / captions / tables / drawings / media_files / ch5_body_paras
                  building_tables / building_tables_cols（建筑基本信息表数量与各表列数）
                  pages / header_pages / footer_pages（需 --pdf）
--expect 键: pages（容差 ±2）/ oMath / captions / tables / drawings / media_files
"""
import argparse
import json
import re
import sys
import zipfile

MARKERS = ["写作参考", "数据参考", "逐月参考", "[FORMULA"]
FLAT_FORMULAS = ["Ejrcn=E", "Eja=ED", "Er=EP", "Vuc=Vk", "Egnm=Egn"]
IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".emf", ".wmf", ".tif", ".tiff")


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


def run(docx: str, pdf: str = None):
    z = zipfile.ZipFile(docx)
    znames = z.namelist()
    doc = z.read("word/document.xml").decode("utf-8", "ignore")
    settings = z.read("word/settings.xml").decode("utf-8", "ignore") if "word/settings.xml" in znames else ""
    headers = {n: z.read(n).decode("utf-8", "ignore") for n in znames if re.fullmatch(r"word/header\d+\.xml", n)}
    footers = {n: z.read(n).decode("utf-8", "ignore") for n in znames if re.fullmatch(r"word/footer\d+\.xml", n)}
    media = [n for n in znames if n.startswith("word/media/") and n.lower().endswith(IMG_EXT)]

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

    checks = {
        "zip_ok": True,
        "toc_field": any("TOC" in s for s in instrs),
        "update_fields": "updateFields" in settings,
        "header_watermark": any(("EAWatermark" in h) or ("behindDoc" in h and "wps:" in h) for h in headers.values()),
        "header_divider": any(("w:pBdr" in h and "w:bottom" in h) for h in headers.values()),
        "footer_page": any("PAGE" in f for f in footers.values()),
        "header_no_vml": not any("v:textpath" in h for h in headers.values()),
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
        hf = ff = 0
        for j in range(n):
            t = d[j].get_text()
            if f"—{j+1}—" in norm(t):
                ff += 1
            if "能源审计报告" in t[:80]:
                hf += 1
        metrics["header_pages"] = "%d/%d" % (hf, n)
        metrics["footer_pages"] = "%d/%d" % (ff, n)
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
