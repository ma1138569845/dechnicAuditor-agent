# -*- coding: utf-8 -*-
"""能源审计报告收尾器（脚本化装配 B2 / T5）

对装配器（build_energy_audit_docx.py）产物做一次 Word COM 收尾：
  打开 → 更新目录域缓存 → Fields.Update → Repaginate → 保存
  → ExportAsFixedFormat（PDF）→ 封面盖章（默认签章/真实印章）

配套约定：
  - 输入 docx 默认与 build 脚本一致：<项目>/output/_script_build/<单位>能源审计报告.docx
  - 输出 pdf 与 docx 同目录同名；盖章位置=封面落款处（y≈0.66·页高，宽 120pt）
  - 收尾后校验/确保 settings 含 updateFields（Word 保存可能剥离，zip 级补写）
  - 报告末打印：页数 / TOC1 条目 / 封面签章图（尺寸+落点）/ updateFields 状态

盖章逻辑移植自 tools/office_seal.py（行为一致：真实印章
tools/energy_audit/assets/default_seal.png 优先，缺失时按审计机构名生成占位红章）。
TOC 刷新配方移植自实战脚本 s20（45 页终稿同款流程）。

用法:
  python finalize_energy_audit_pdf.py --project-dir <项目目录>
      [--docx <输入docx>] [--pdf <输出pdf>] [--no-seal] [--seal-text <盖章文字>]
"""
import argparse
import os
import re
import shutil
import sys
import tempfile
import time
import zipfile

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# skills/energy-audit/energy-audit-report/scripts -> repo 根（发布到 profile 后可能不存在）
_REPO_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", "..", "..", ".."))

# 默认签章落点（与 tools/office_seal.py 一致）：封面底部居中。
_DEFAULT_SEAL_WIDTH_PT = 120.0
_DEFAULT_SEAL_Y_RATIO = 0.66


def _find_default_seal():
    """真实印章 PNG：repo tools/energy_audit/assets/ 或 cwd 下同名路径。"""
    for base in (_REPO_ROOT, os.getcwd()):
        p = os.path.join(base, "tools", "energy_audit", "assets", "default_seal.png")
        if os.path.isfile(p):
            return p
    return None


# ---------------------------------------------------------------- 签章（移植自 tools/office_seal.py）

_CJK_FONT_CANDIDATES = (
    "C:/Windows/Fonts/simsun.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/msyhbd.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)


def _load_cjk_font(size):
    from PIL import ImageFont
    for path in _CJK_FONT_CANDIDATES:
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _wrap_text(text, max_per_line=8):
    text = (text or "").strip()
    if not text:
        return [""]
    if len(text) <= max_per_line:
        return [text]
    idx = text.find("）")
    if 0 < idx <= max_per_line - 1:
        return [text[: idx + 1], text[idx + 1:]]
    mid = (len(text) + 1) // 2
    return [text[:mid], text[mid:]]


def _make_default_seal(text, size=480):
    """按审计机构名生成红色圆形占位签章（透明背景 PNG）。"""
    from PIL import Image, ImageDraw
    fd, out_path = tempfile.mkstemp(suffix=".png", prefix="ea_seal_")
    os.close(fd)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    red = (200, 22, 22, 255)
    margin = int(size * 0.05)
    draw.ellipse([margin, margin, size - margin, size - margin], outline=red,
                 width=int(size * 0.030))
    inner = int(size * 0.15)
    draw.ellipse([inner, inner, size - inner, size - inner], outline=red,
                 width=int(size * 0.015))
    lines = _wrap_text(text)
    inner_diameter = size * 0.7
    max_chars = max((len(line) for line in lines), default=1)
    font_size = max(24, int(inner_diameter * 0.9 / max_chars))
    font = _load_cjk_font(font_size)
    star_font = _load_cjk_font(int(size * 0.14))
    line_height = int(font_size * 1.4)
    y = (size - line_height * len(lines)) / 2
    for line in lines:
        box = draw.textbbox((0, 0), line, font=font)
        draw.text(((size - (box[2] - box[0])) / 2, y), line, fill=red, font=font)
        y += line_height
    star = "★"
    sbox = draw.textbbox((0, 0), star, font=star_font)
    draw.text(((size - (sbox[2] - sbox[0])) / 2, size * 0.62), star, fill=red,
              font=star_font)
    img.save(out_path)
    return out_path


def _stamp_pdf(pdf_path, seal_image_path, page_index=0):
    """把签章图片叠加到 PDF 封面（落款处），原地覆盖（临时文件+原子替换）。"""
    import pymupdf
    doc = pymupdf.open(pdf_path)
    try:
        page = doc[page_index]
        cx = page.rect.width / 2
        cy = page.rect.height * _DEFAULT_SEAL_Y_RATIO
        w = _DEFAULT_SEAL_WIDTH_PT
        rect = pymupdf.Rect(cx - w / 2, cy - w / 2, cx + w / 2, cy + w / 2)
        page.insert_image(rect, filename=seal_image_path, overlay=True)
        fd, tmp = tempfile.mkstemp(suffix=".pdf", prefix="ea_seal_")
        os.close(fd)
        try:
            doc.save(tmp)
        finally:
            doc.close()
        try:
            os.replace(tmp, pdf_path)
        finally:
            if os.path.exists(tmp):
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
    finally:
        try:
            doc.close()
        except Exception:
            pass


def stamp_pdf_with_default_seal(pdf_path, seal_text):
    """优先真实印章图（存在即用，忽略文字）；否则生成占位章（用完即删）。"""
    real = _find_default_seal()
    cleanup = False
    if real:
        seal_png = real
    else:
        seal_png = _make_default_seal(seal_text)
        cleanup = True
    try:
        _stamp_pdf(pdf_path, seal_png)
    finally:
        if cleanup:
            try:
                os.unlink(seal_png)
            except OSError:
                pass


# ---------------------------------------------------------------- Word COM 收尾

def _word_finalize(tmp_docx, tmp_pdf):
    """打开 docx → 更新目录域 → 保存 → 导出 PDF；返回 (页数, TOC 对象数)。"""
    import win32com.client as win32
    word = win32.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    pages = None
    n_toc = 0
    try:
        doc = word.Documents.Open(tmp_docx, ReadOnly=False, AddToRecentFiles=False,
                                  ConfirmConversions=False)
        try:
            n_toc = doc.TablesOfContents.Count
            if n_toc:
                doc.TablesOfContents(1).Update()
            doc.Fields.Update()
            doc.Repaginate()
            pages = doc.ComputeStatistics(2)  # wdStatisticPages
            doc.Save()
            doc.ExportAsFixedFormat(tmp_pdf, 17)  # 17 = wdExportFormatPDF
        finally:
            doc.Close(False)
    finally:
        try:
            word.Quit()
        except Exception as e:
            print("word quit warn:", e)
    return pages, n_toc


def _replace_retry(src, dst, attempts=6, delay=0.8):
    """Word 关闭后句柄可能短暂占用，重试原子替换。"""
    for k in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if k == attempts - 1:
                raise
            time.sleep(delay)


def _ensure_update_fields_zip(path):
    """确保 settings 含 updateFields（Word 保存可能剥离）；返回是否补写。"""
    with zipfile.ZipFile(path) as z:
        s = z.read("word/settings.xml").decode("utf-8")
        if "updateFields" in s:
            return False
        items = [(i, z.read(i.filename)) for i in z.infolist()]
    s2 = s.replace("</w:settings>", '<w:updateFields w:val="true"/></w:settings>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for item, data in items:
            if item.filename == "word/settings.xml":
                data = s2.encode("utf-8")
            z.writestr(item, data)
    return True


def _toc1_entries(path):
    with zipfile.ZipFile(path) as z:
        x = z.read("word/document.xml").decode("utf-8", "ignore")
    out = []
    for m in re.finditer(r"<w:p [^>]*>.*?</w:p>", x, re.S):
        if '<w:pStyle w:val="TOC1"/>' in m.group(0):
            out.append("".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", m.group(0))))
    return out


def finalize(project_dir, docx=None, pdf=None, seal=True, seal_text=None):
    import json
    project_dir = os.path.abspath(project_dir)
    with open(os.path.join(project_dir, "data.json"), encoding="utf-8") as f:
        data = json.load(f)
    base = data.get("base", {})
    unit = base.get("unit_name") or "××单位"
    org = seal_text or base.get("audit_org_name") or ""

    outdir = os.path.join(project_dir, "output", "_script_build")
    docx = os.path.abspath(docx or os.path.join(outdir, f"{unit}能源审计报告.docx"))
    pdf = os.path.abspath(pdf or os.path.join(outdir, f"{unit}能源审计报告.pdf"))
    if not os.path.isfile(docx):
        raise FileNotFoundError(f"缺装配产物 docx: {docx}")
    os.makedirs(os.path.dirname(pdf), exist_ok=True)

    tmp_docx = os.path.join(os.path.dirname(pdf), "_finalize_tmp.docx")
    tmp_pdf = os.path.join(os.path.dirname(pdf), "_finalize_tmp.pdf")
    for p in (tmp_docx, tmp_pdf):
        if os.path.exists(p):
            os.remove(p)

    shutil.copy(docx, tmp_docx)
    pages, n_toc = _word_finalize(tmp_docx, tmp_pdf)
    _replace_retry(tmp_docx, docx)
    _replace_retry(tmp_pdf, pdf)

    fixed = _ensure_update_fields_zip(docx)
    toc1 = _toc1_entries(docx)

    seal_note = "跳过（--no-seal）"
    if seal:
        if org:
            stamp_pdf_with_default_seal(pdf, org)
            source = "真实印章" if _find_default_seal() else "占位章"
            seal_note = f"已盖章（{source}：{org}）"
        else:
            seal_note = "跳过（无审计机构名）"

    # 封面签章图核验（尺寸+落点）
    seal_info = "无封面图"
    try:
        import pymupdf
        d = pymupdf.open(pdf)
        p1 = d[0]
        for im in p1.get_images(full=True):
            rects = p1.get_image_rects(im[0])
            for r in rects:
                seal_info = (f"p1 img {im[2]}x{im[3]} "
                             f"@ycenter {(r.y0 + r.y1) / 2 / p1.rect.height:.2f}")
        d.close()
    except Exception as e:
        seal_info = f"核验失败: {e}"

    print(f"OK -> {docx}")
    print(f"OK -> {pdf}")
    print(f"  pages={pages} | TOC 对象={n_toc} | TOC1 条目={len(toc1)}")
    print(f"  updateFields 补写={'是' if fixed else '否（已存在）'}")
    print(f"  盖章: {seal_note} | 封面图: {seal_info}")
    for t in toc1:
        print("   |", t[:60])
    return docx, pdf


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="能源审计报告收尾器（T5：Word COM 刷新目录 + 导出签章 PDF）")
    ap.add_argument("--project-dir", required=True, help="项目目录（含 data.json）")
    ap.add_argument("--docx", help="输入 docx（默认 output/_script_build/<单位>能源审计报告.docx）")
    ap.add_argument("--pdf", help="输出 pdf（默认与 docx 同目录同名）")
    ap.add_argument("--no-seal", action="store_true", help="跳过盖章")
    ap.add_argument("--seal-text", help="盖章文字（默认 data.json audit_org_name）")
    a = ap.parse_args(argv)
    finalize(a.project_dir, a.docx, a.pdf, seal=not a.no_seal, seal_text=a.seal_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
