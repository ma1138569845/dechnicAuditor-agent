#!/usr/bin/env python3
"""Recalculate .xlsx formulas via local Microsoft Excel COM automation.

openpyxl writes formula strings but never computes their cached values. Excel
recalculates on open (and on an explicit ``CalculateFullRebuild``), so opening
+ saving through COM produces a workbook whose formula results are readable by
``openpyxl(..., data_only=True)``.

This module is deliberately light on import side effects: only the standard
library is imported at module load; ``win32com`` is imported lazily inside the
function. It is the Excel-COM counterpart to :mod:`tools.office_pdf_convert`,
shared by the xlsx ``xlsx_recalc.py`` and finance ``recalc.py`` skill scripts.
"""

from __future__ import annotations

import os

# xlOpenXMLWorkbook — forces a clean .xlsx when saving to a new path.
_XL_OPENXML_WORKBOOK = 51
# xlUpdateLinksNever — suppress the "update external links?" prompt.
_XL_UPDATE_LINKS_NEVER = 0


def recalc_via_com(xlsx_path: str, out_path: str | None = None) -> str:
    """Recalculate an .xlsx workbook via Excel COM and return the output path.

    When ``out_path`` is None the input file is recalculated in place (keeping
    its original format); otherwise the result is saved as .xlsx to ``out_path``.
    Raises RuntimeError when pywin32 or Excel is unavailable, or when Excel
    fails to open/recalculate/save the workbook.
    """
    try:
        import win32com.client
    except ImportError as exc:  # pragma: no cover - Windows-only path
        raise RuntimeError(
            "pywin32 not installed — Excel COM recalc unavailable. "
            "Install Microsoft Excel or LibreOffice."
        ) from exc

    if not os.path.isfile(xlsx_path):
        raise RuntimeError(f"no such file: {xlsx_path}")

    app = win32com.client.DispatchEx("Excel.Application")
    app.Visible = False
    app.DisplayAlerts = False
    workbook = None
    try:
        workbook = app.Workbooks.Open(
            xlsx_path, ReadOnly=False, UpdateLinks=_XL_UPDATE_LINKS_NEVER)
        # Full dependency-chain rebuild + recompute, regardless of the
        # workbook's cached calculation mode.
        app.CalculateFullRebuild()

        if out_path:
            workbook.SaveAs(
                os.path.abspath(out_path), FileFormat=_XL_OPENXML_WORKBOOK)
        else:
            workbook.Save()
    finally:
        # Best-effort cleanup: each step may itself raise when Excel is
        # already in a bad state, so never let one failure block the rest or
        # leave an orphaned Excel process behind.
        if workbook is not None:
            try:
                workbook.Close(False)  # False = do not re-save on close
            except Exception:
                pass
        try:
            app.Quit()
        except Exception:
            pass
        del workbook, app

    result = os.path.abspath(out_path) if out_path else xlsx_path
    if not os.path.isfile(result):
        raise RuntimeError("Excel COM recalc produced no output file")
    return result
