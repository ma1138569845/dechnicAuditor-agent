#!/usr/bin/env python3
"""Office -> PDF conversion with a degradation chain: OnlyOffice -> COM.

This module is deliberately light on import side effects: it imports only the
standard library at module load. OnlyOffice (``tools.office_onlyoffice``) and
win32com are imported lazily inside the conversion functions, so importing this
module never pulls in the DocumentServer or pywin32 stacks unless a conversion
actually runs.

It is shared by the ``office_editor`` toolset (``tools.office_editor_tool``)
and the docx/pptx productivity skills, so the "convert to PDF" logic lives in
one place rather than being duplicated per caller.
"""

from __future__ import annotations

import os
import tempfile


def com_to_pdf(file_path: str, doc_type: str) -> str:
    """Convert an Office file to PDF via local Microsoft Office COM automation.

    Windows-only. Requires pywin32 and a locally installed Word/Excel/PowerPoint.
    Raises RuntimeError on failure so callers can surface a clear message.
    """
    try:
        import win32com.client
    except ImportError as exc:  # pragma: no cover - Windows-only path
        raise RuntimeError(
            "pywin32 not installed — COM conversion unavailable. "
            "Install Microsoft Office or configure OnlyOffice."
        ) from exc

    out_path = os.path.join(
        tempfile.gettempdir(), f"hermes_com_{os.path.basename(file_path)}.pdf")

    if doc_type == "doc":
        app = win32com.client.DispatchEx("Word.Application")
        app.Visible = False
        try:
            document = app.Documents.Open(file_path, ReadOnly=True)
            document.ExportAsFixedFormat(out_path, 17)  # 17 = wdExportFormatPDF
            document.Close(False)
        finally:
            app.Quit()
    elif doc_type == "sheet":
        app = win32com.client.DispatchEx("Excel.Application")
        app.Visible = False
        app.DisplayAlerts = False
        try:
            workbook = app.Workbooks.Open(file_path, ReadOnly=True)
            workbook.ExportAsFixedFormat(0, out_path)  # 0 = xlTypePDF
            workbook.Close(False)
        finally:
            app.Quit()
    elif doc_type == "slide":
        app = win32com.client.DispatchEx("PowerPoint.Application")
        try:
            presentation = app.Presentations.Open(
                file_path, ReadOnly=True, WithWindow=False)
            presentation.ExportAsFixedFormat(out_path, 2)  # 2 = ppFixedFormatTypePDF
            presentation.Close()
        finally:
            app.Quit()
    else:
        raise RuntimeError(f"unsupported doc_type for COM conversion: {doc_type}")

    if not os.path.isfile(out_path):
        raise RuntimeError("COM conversion produced no PDF output")
    return out_path


def office_to_pdf(file_path: str, doc_type: str) -> str:
    """Office -> PDF via OnlyOffice ConvertService first, COM automation fallback.

    Raises RuntimeError when both paths are unavailable or fail.
    """
    # 1. OnlyOffice ConvertService (lazy import keeps import side effects low).
    try:
        from tools.office_onlyoffice import convert_to_pdf as _onlyoffice_convert
        pdf_path = _onlyoffice_convert(file_path, doc_type)
        if pdf_path and os.path.isfile(pdf_path):
            return pdf_path
    except Exception:
        # OnlyOffice disabled/unreachable/conversion failed — fall through to COM.
        pass

    # 2. COM automation fallback.
    return com_to_pdf(file_path, doc_type)
