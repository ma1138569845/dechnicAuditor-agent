#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fix_chapter5_formulas.py — 把 5.3 节纯文本公式段替换为正式报告同款 OMML 分式公式。

用法:
    python fix_chapter5_formulas.py <报告.docx> [--dry-run]

背景（2026-09-05）:
- 当前生成报告的 5.3 节公式是纯文本（如 `Ejfgn=（E−Egn−Ejt）/M`），
  正式报告为 OMML 公式（m:f 分数线 + m:sSub 下标）。
- officecli equation 元素不支持分式（实测 \\frac 不解析、m:f=0），
  故本脚本用 zip+lxml 直接注入 OMML XML，结构按正式报告 dump 修正。
- 符号以正式报告为准: Ejfgn / Ejd / Er / Vuc / Egnm。
"""
import argparse
import re
import shutil
import sys
import zipfile
from pathlib import Path

from lxml import etree

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"

M = f"{{{M_NS}}}"


def _run(text):
    r = etree.Element(M + "r")
    t = etree.Element(M + "t")
    t.text = text
    r.append(t)
    return r


def _ssub(base, sub):
    """m:sSub: 基底在 m:e、下标在 m:sub（正式报告结构）"""
    el = etree.Element(M + "sSub")
    e = etree.SubElement(el, M + "e")
    e.append(_run(base))
    s = etree.SubElement(el, M + "sub")
    s.append(_run(sub))
    return el


def _frac(num_children, den_children):
    el = etree.Element(M + "f")
    num = etree.SubElement(el, M + "num")
    for c in num_children:
        num.append(c)
    den = etree.SubElement(el, M + "den")
    for c in den_children:
        den.append(c)
    return el


def _build_omath(symbol):
    """五个公式的 OMML 构造（符号对齐正式报告）"""
    om = etree.Element(M + "oMath")
    if symbol == "Ejfgn":
        children = [
            _ssub("E", "jfgn"),
            _run("="),
            _frac([_run("E−"), _ssub("E", "gn"), _run("−"), _ssub("E", "jt")],
                  [_run("M")]),
        ]
    elif symbol == "Ejd":
        children = [
            _ssub("E", "jd"),
            _run("="),
            _frac([_ssub("E", "D")], [_run("M")]),
        ]
    elif symbol == "Er":
        children = [
            _ssub("E", "r"),
            _run("="),
            _frac([_run("E")], [_run("P")]),
        ]
    elif symbol == "Vuc":
        children = [
            _ssub("V", "uc"),
            _run("="),
            _frac([_ssub("V", "k")], [_ssub("N", "p")]),
        ]
    elif symbol == "Vz":
        # 医疗：Vz = Vk × 1000 / (Nbed × 365)
        children = [
            _ssub("V", "z"),
            _run("="),
            _frac([_ssub("V", "k"), _run("×1000")],
                  [_ssub("N", "bed"), _run("×365")]),
        ]
    elif symbol == "Vam":
        # 政务/场馆：Vam = Vk / M
        children = [
            _ssub("V", "am"),
            _run("="),
            _frac([_ssub("V", "k")], [_run("M")]),
        ]
    elif symbol == "Egnm":
        children = [
            _ssub("E", "gnm"),
            _run("="),
            _frac([_ssub("E", "gn")], [_ssub("M", "gn")]),
        ]
    else:
        raise ValueError(f"未知公式符号: {symbol}")
    for c in children:
        om.append(c)
    return om


SYMBOLS = ["Ejfgn", "Ejd", "Er", "Vuc", "Vz", "Vam", "Egnm"]


def _match_symbol(p_text):
    """段落文本归一化后是否以某个公式符号开头（去空格/括号/斜杠/等号）"""
    norm = re.sub(r"[\s（）()/＝=:：]+", "", p_text)
    for sym in SYMBOLS:
        if norm.startswith(sym):
            return sym
    return None


def process_docx(path, dry_run=False):
    src = Path(path)
    if not src.exists():
        print(f"文件不存在: {src}")
        return 1

    tmp = src.with_suffix(".fixformula.tmp")
    shutil.copy2(src, tmp)

    replaced = 0
    try:
        with zipfile.ZipFile(tmp, "r") as zin:
            names = zin.namelist()
            entries = {n: zin.read(n) for n in names}

        root = etree.fromstring(entries["word/document.xml"])
        # 根元素注册 m 前缀（若未声明）
        if M_NS not in (root.nsmap or {}).values():
            prefix = (root.nsmap or {}).get(M_NS, "m")
            root.attrib[f"xmlns:{prefix}"] = M_NS

        body = root.find(f"{{{W_NS}}}body")
        if body is None:
            print("找不到 w:body")
            return 1

        for p in body.findall(f".//{{{W_NS}}}p"):
            texts = [t.text or "" for t in p.findall(f".//{{{W_NS}}}t")]
            full = "".join(texts).strip()
            if not full or "=" not in full:
                continue
            sym = _match_symbol(full)
            if not sym:
                continue
            if p.find(f".//{M}oMath") is not None:
                continue  # 已是 OMML 公式
            for child in list(p):
                if etree.QName(child).localname != "pPr":
                    p.remove(child)
            omp = etree.SubElement(p, M + "oMathPara")
            omp.append(_build_omath(sym))
            replaced += 1
            print(f"  替换公式: {sym}  ← 原文段: {full[:50]}")

        entries["word/document.xml"] = etree.tostring(
            root, xml_declaration=True, encoding="UTF-8", standalone=True
        )

        if dry_run:
            print(f"[dry-run] 共发现 {replaced} 个文本公式，未写入")
        else:
            with zipfile.ZipFile(src, "w", zipfile.ZIP_DEFLATED) as zout:
                for n in names:
                    zout.writestr(n, entries[n])
            print(f"完成: 已替换 {replaced} 个公式 → {src}")

        return 0
    finally:
        if tmp.exists():
            tmp.unlink()


def main():
    ap = argparse.ArgumentParser(description="5.3 节文本公式 → OMML 公式注入")
    ap.add_argument("docx", help="报告 docx 路径")
    ap.add_argument("--dry-run", action="store_true", help="只报告不写入")
    args = ap.parse_args()
    sys.exit(process_docx(args.docx, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
