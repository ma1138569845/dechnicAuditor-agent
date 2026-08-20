#!/usr/bin/env python3
"""Recalculate an .xlsx file's formulas headlessly.

Usage: python recalc.py <path.xlsx> [timeout_seconds]

openpyxl writes formula strings but does not compute them. Downstream scripts
that open the file with data_only=True get None for every formula cell until
something has actually calculated the workbook. Excel does this on open;
headless pipelines need a recalculation engine to do it explicitly.

Preference order: local Excel COM automation (Windows), then LibreOffice
(`soffice`) as a fallback for non-Windows / no-Office environments.

Exits 0 on success (workbook recomputed and resaved in place), non-zero on
failure. Writes status JSON to stdout either way.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def find_libreoffice() -> str | None:
    for cmd in ("libreoffice", "soffice"):
        path = shutil.which(cmd)
        if path:
            return path
    return None


def _find_repo_root() -> str | None:
    """Locate the repo root (the directory containing ``tools/``) from __file__."""
    current = os.path.dirname(os.path.realpath(__file__))
    for _ in range(8):
        if os.path.isfile(os.path.join(current, "tools", "office_excel_recalc.py")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent
    return None


def _recalc_via_com(src: Path) -> str | None:
    """Recalculate via Excel COM (no LibreOffice required).

    Returns the output path, or None when the shared converter is unavailable
    or fails — callers then fall back to soffice.
    """
    try:
        root = _find_repo_root()
        if root and root not in sys.path:
            sys.path.insert(0, root)
        from tools.office_excel_recalc import recalc_via_com
        return recalc_via_com(str(src))
    except Exception:
        return None


def recalc(xlsx_path: str, timeout: int = 60) -> dict:
    src = Path(xlsx_path).resolve()
    if not src.exists():
        return {"status": "error", "error": f"File not found: {src}"}

    # 1. Prefer Excel COM (no LibreOffice dependency).
    output = _recalc_via_com(src)
    if output is not None:
        return {"status": "success", "file": str(output)}

    # 2. Fall back to LibreOffice.
    lo = find_libreoffice()
    if lo is None:
        return {
            "status": "error",
            "error": "no recalc engine — install Microsoft Excel (Windows) "
                     "or LibreOffice, or recalc in a real Excel session",
        }

    with tempfile.TemporaryDirectory() as td:
        try:
            subprocess.run(
                [
                    lo,
                    "--headless",
                    "--calc",
                    "--convert-to",
                    "xlsx",
                    str(src),
                    "--outdir",
                    td,
                ],
                check=True,
                capture_output=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return {"status": "error", "error": f"libreoffice timed out after {timeout}s"}
        except subprocess.CalledProcessError as e:
            return {
                "status": "error",
                "error": f"libreoffice exited {e.returncode}: {e.stderr.decode(errors='replace')[:500]}",
            }

        produced = Path(td) / src.name
        if not produced.exists():
            return {"status": "error", "error": "libreoffice did not produce output file"}

        shutil.copy(produced, src)

    return {"status": "success", "file": str(src)}


def main():
    if len(sys.argv) < 2:
        print("Usage: python recalc.py <path.xlsx> [timeout_seconds]", file=sys.stderr)
        sys.exit(2)
    timeout = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    result = recalc(sys.argv[1], timeout=timeout)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["status"] == "success" else 1)


if __name__ == "__main__":
    main()
