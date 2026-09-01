#!/usr/bin/env python3
"""默认签章生成 + PDF 盖章（方案 A：pymupdf 叠加签章到封面）。

能源审计报告最终产物包含一份加盖签章的 PDF。签章默认由 PIL 生成红色
圆形章（占位方案），后续可替换为审计机构的真实印章图片。

设计：
- ``make_default_seal`` — 用 Pillow 生成红色圆形默认签章（透明背景 PNG）。
- ``stamp_pdf`` — 用 pymupdf 把签章图片叠加到 PDF 指定页（默认封面）。

两个函数都延迟导入重依赖（Pillow / pymupdf），保持模块导入零副作用，
与 ``tools.office_pdf_convert`` 的约定一致。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional, Sequence, Tuple

# 签章默认落点：封面底部居中（审计机构名称处，build_cover 用
# space_before=Pt(420) 把落款推到页面下部）。
_DEFAULT_SEAL_WIDTH_PT = 120.0
_DEFAULT_SEAL_Y_RATIO = 0.66

# 默认签章图片：存在则优先用真实签章（审计机构印章 PNG），否则回退到
# 代码生成的占位章。把真实印章放到 tools/energy_audit/assets/default_seal.png
# 即自动生效，无需改代码。
_DEFAULT_SEAL_PNG = (
    Path(__file__).resolve().parent / "energy_audit" / "assets" / "default_seal.png"
)

# 常见中文字体（按优先级），公章文字用宋体。
_CJK_FONT_CANDIDATES = (
    "C:/Windows/Fonts/simsun.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/msyhbd.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)


def _load_cjk_font(size: int):
    """按优先级加载第一个可用的中文字体；失败时退回 PIL 默认字体。"""
    from PIL import ImageFont

    for path in _CJK_FONT_CANDIDATES:
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:  # pragma: no cover - 损坏字体
                continue
    return ImageFont.load_default()


def _wrap_text(text: str, max_per_line: int = 8) -> list[str]:
    """把长机构名拆成居中显示的多行（优先在右括号后分行，最多两行）。"""
    text = (text or "").strip()
    if not text:
        return [""]
    if len(text) <= max_per_line:
        return [text]
    # 优先在右括号"）"后分行（"公司（地区）..."常见结构）
    idx = text.find("）")
    if 0 < idx <= max_per_line - 1:
        return [text[: idx + 1], text[idx + 1 :]]
    # 无括号：中点平分（最多两行）
    mid = (len(text) + 1) // 2
    return [text[:mid], text[mid:]]


def make_default_seal(
    text: str,
    out_path: Optional[str] = None,
    size: int = 480,
) -> str:
    """生成红色圆形默认签章（透明背景 PNG）。

    Args:
        text: 签章中心文字（审计机构名称），长文自动拆两行。
        out_path: 输出 PNG 路径；``None`` 时写入临时目录。
        size: 图片边长（像素）。

    Returns:
        生成的 PNG 文件路径。
    """
    from PIL import Image, ImageDraw

    if out_path is None:
        fd, out_path = tempfile.mkstemp(suffix=".png", prefix="hermes_seal_")
        os.close(fd)

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    red = (200, 22, 22, 255)

    # 外圈 + 内圈圆环
    margin = int(size * 0.05)
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        outline=red,
        width=int(size * 0.030),
    )
    inner = int(size * 0.15)
    draw.ellipse(
        [inner, inner, size - inner, size - inner],
        outline=red,
        width=int(size * 0.015),
    )

    # 中心文字（自然分行 + 动态字体适配内圈，避免溢出画布）
    lines = _wrap_text(text)
    inner_diameter = size * 0.7  # 内圈直径
    max_chars = max((len(line) for line in lines), default=1)
    font_size = max(24, int(inner_diameter * 0.9 / max_chars))
    font = _load_cjk_font(font_size)
    star_font = _load_cjk_font(int(size * 0.14))
    line_height = int(font_size * 1.4)
    total_height = line_height * len(lines)
    y = (size - total_height) / 2
    for line in lines:
        box = draw.textbbox((0, 0), line, font=font)
        w = box[2] - box[0]
        draw.text(((size - w) / 2, y), line, fill=red, font=font)
        y += line_height

    # 底部五角星
    star = "★"
    sbox = draw.textbbox((0, 0), star, font=star_font)
    sw = sbox[2] - sbox[0]
    draw.text(
        ((size - sw) / 2, size * 0.62),
        star,
        fill=red,
        font=star_font,
    )

    img.save(out_path)
    return out_path


def stamp_pdf(
    pdf_path: str,
    seal_image_path: str,
    page_index: int = 0,
    position: Optional[Tuple[float, float]] = None,
    seal_width: float = _DEFAULT_SEAL_WIDTH_PT,
    out_path: Optional[str] = None,
) -> str:
    """把签章图片叠加到 PDF 指定页（默认封面），返回盖章后的 PDF 路径。

    Args:
        pdf_path: 待盖章的 PDF 路径。
        seal_image_path: 签章 PNG 路径（透明背景）。
        page_index: 盖章页码（0=封面）。
        position: 签章中心点 ``(cx, cy)``（pt）；``None`` 时用默认落点
            （封面底部居中，审计机构名称附近）。
        seal_width: 签章宽度（pt，等比缩放）。
        out_path: 输出 PDF 路径；``None`` 时覆盖原文件。

    Returns:
        盖章后的 PDF 路径。
    """
    import pymupdf

    if not os.path.isfile(pdf_path):
        raise FileNotFoundError(pdf_path)
    if not os.path.isfile(seal_image_path):
        raise FileNotFoundError(seal_image_path)

    doc = pymupdf.open(pdf_path)
    try:
        if page_index < 0 or page_index >= len(doc):
            raise IndexError(f"page_index {page_index} out of range (0..{len(doc)-1})")

        page = doc[page_index]
        seal_w = float(seal_width)
        seal_h = seal_w  # 正方形签章

        if position is None:
            cx = page.rect.width / 2
            cy = page.rect.height * _DEFAULT_SEAL_Y_RATIO
        else:
            cx, cy = float(position[0]), float(position[1])

        rect = pymupdf.Rect(
            cx - seal_w / 2,
            cy - seal_h / 2,
            cx + seal_w / 2,
            cy + seal_h / 2,
        )
        page.insert_image(rect, filename=seal_image_path, overlay=True)

        out = out_path or pdf_path
        # 先写临时文件并关闭 doc（释放原文件句柄），再原子替换到目标，
        # 避免 Windows 下覆盖被占用的原文件失败。
        fd, tmp = tempfile.mkstemp(suffix=".pdf", prefix="hermes_seal_")
        os.close(fd)
        try:
            doc.save(tmp)
        finally:
            doc.close()
        try:
            os.replace(tmp, out)
        finally:
            if os.path.exists(tmp):
                try:
                    os.unlink(tmp)
                except OSError:  # pragma: no cover - 清理失败不阻断
                    pass
        return out
    finally:
        # doc 已在保存路径关闭；兜底避免重复 close 报错。
        try:
            doc.close()
        except Exception:  # pragma: no cover - 重复 close 是安全的 no-op
            pass


def stamp_pdf_with_default_seal(
    pdf_path: str,
    seal_text: str,
    page_index: int = 0,
    position: Optional[Tuple[float, float]] = None,
    seal_width: float = _DEFAULT_SEAL_WIDTH_PT,
    out_path: Optional[str] = None,
) -> str:
    """盖章到 PDF（便捷入口）：优先用真实签章图，否则生成默认占位章。

    真实签章：``_DEFAULT_SEAL_PNG`` 存在时直接使用（``seal_text`` 忽略）；
    否则用 ``seal_text`` 生成红色圆形默认章（用完即删）。
    """
    cleanup = False
    if _DEFAULT_SEAL_PNG.is_file():
        seal_png = str(_DEFAULT_SEAL_PNG)
    else:
        seal_png = make_default_seal(seal_text)
        cleanup = True
    try:
        return stamp_pdf(
            pdf_path,
            seal_png,
            page_index=page_index,
            position=position,
            seal_width=seal_width,
            out_path=out_path,
        )
    finally:
        if cleanup:
            try:
                os.unlink(seal_png)
            except OSError:  # pragma: no cover - 清理临时签章失败不阻断
                pass
