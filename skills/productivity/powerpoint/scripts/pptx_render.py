#!/usr/bin/env python3
"""Render every slide of a .pptx to per-slide PNG images.

Pipeline: convert the deck to PDF via OnlyOffice (Microsoft Office COM
automation fallback) or LibreOffice (soffice) as a last resort, then poppler
(pdftoppm, or pdftocairo as an alternate) splits the PDF into one PNG per slide.

Output is JSON. When a conversion path is available:
  {"rendered": true, "files": ["render/slide-1.png", ...]}
When no conversion path is available the script still exits 0 and reports:
  {"rendered": false, "missing": ["soffice"], "guidance": "..."}
so callers can degrade gracefully (fall back to pptx_read.py --outline).
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile


def _find_repo_root():
    """Locate the repo root (the directory containing ``tools/``) from __file__."""
    current = os.path.dirname(os.path.realpath(__file__))
    for _ in range(8):
        if os.path.isfile(os.path.join(current, "tools", "office_pdf_convert.py")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent
    return None


def _office_to_pdf(pptx_path):
    """Convert the deck via OnlyOffice (then COM) — no LibreOffice required.

    Returns a PDF path, or None when the shared converter is unavailable or
    fails; callers then fall back to soffice.
    """
    try:
        root = _find_repo_root()
        if root and root not in sys.path:
            sys.path.insert(0, root)
        from tools.office_pdf_convert import office_to_pdf
        pdf = office_to_pdf(pptx_path, "slide")
        return pdf if pdf and os.path.exists(pdf) else None
    except Exception:
        return None


def find_tools():
    """Return (soffice, splitter, missing) using shutil.which."""
    soffice = shutil.which("soffice")
    splitter = shutil.which("pdftoppm") or shutil.which("pdftocairo")
    missing = []
    if not soffice:
        missing.append("soffice")
    if not splitter:
        missing.append("pdftoppm (or pdftocairo)")
    return soffice, splitter, missing


def _soffice_to_pdf(soffice, pptx_path, tmp):
    proc = subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf",
         "--outdir", tmp, pptx_path],
        capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=300)
    pdfs = glob.glob(os.path.join(tmp, "*.pdf"))
    if proc.returncode != 0 or not pdfs:
        raise SystemExit(f"soffice PDF conversion failed: {proc.stderr}")
    return pdfs[0]


def _rasterize(splitter, pdf, out_prefix, dpi):
    proc = subprocess.run(
        [splitter, "-png", "-r", str(dpi), pdf, out_prefix],
        capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=300)
    if proc.returncode != 0:
        raise SystemExit(f"{os.path.basename(splitter)} failed: {proc.stderr}")
    return sorted(glob.glob(out_prefix + "*.png"))


def render(pptx_path, out_dir, prefix, dpi):
    soffice, splitter, missing = find_tools()
    if not splitter:
        return {
            "rendered": False, "missing": ["pdftoppm (or pdftocairo)"],
            "guidance": "Install poppler-utils (pdftoppm/pdftocairo) to split "
                        "PDF pages into PNGs. Without it, verify decks with "
                        "pptx_read.py --outline instead.",
        }

    os.makedirs(out_dir, exist_ok=True)
    out_prefix = os.path.join(out_dir, prefix)

    # 1. Prefer OnlyOffice -> COM (no LibreOffice dependency).
    pdf = _office_to_pdf(pptx_path)
    if pdf is not None:
        return {"rendered": True, "files": _rasterize(splitter, pdf, out_prefix, dpi)}

    # 2. Fall back to LibreOffice if the shared converter is unavailable.
    if not soffice:
        return {
            "rendered": False, "missing": ["soffice"],
            "guidance": "Install LibreOffice (soffice) or configure OnlyOffice "
                        "/ Microsoft Office to render slides. Without them, "
                        "verify decks with pptx_read.py --outline instead.",
        }

    with tempfile.TemporaryDirectory() as tmp:
        pdf = _soffice_to_pdf(soffice, pptx_path, tmp)
        files = _rasterize(splitter, pdf, out_prefix, dpi)
    return {"rendered": True, "files": files}


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        description="Render each slide of a .pptx to a PNG via "
                    "OnlyOffice/COM (soffice fallback) + pdftoppm/pdftocairo.",
        epilog=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pptx", help="path to the .pptx file")
    parser.add_argument("--outdir", default="render",
                        help="directory for PNGs (default: ./render)")
    parser.add_argument("--prefix", default="slide",
                        help="PNG filename prefix (default: slide)")
    parser.add_argument("--dpi", type=int, default=100,
                        help="render resolution (default: 100)")
    args = parser.parse_args(argv)

    result = render(args.pptx, args.outdir, args.prefix, args.dpi)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
