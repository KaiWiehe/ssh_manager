from __future__ import annotations

import csv
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from xml.sax.saxutils import escape

from .dialogs_export import EXPORT_COLUMNS
from .models import Session


ExportGroup = tuple[str, list[Session]]


def export_column_label(key: str) -> str:
    return dict(EXPORT_COLUMNS)[key]


def export_value(session: Session, field: str, notes_getter) -> str:
    if field == "notes":
        return notes_getter(session.key)
    if field == "port":
        return str(session.port)
    return str(getattr(session, field, ""))


def folder_export_title(folder_key: str) -> str:
    return folder_key or "Verbindungen ohne Ordner"


def write_csv_export(path: str | Path, groups: list[ExportGroup], fields: list[str], notes_getter) -> None:
    """Write grouped connection tables to a UTF-8 CSV that Excel opens cleanly."""
    with Path(path).open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file, delimiter=";")
        for index, (folder_key, sessions) in enumerate(groups):
            if index:
                writer.writerow([])
            writer.writerow([folder_export_title(folder_key)])
            writer.writerow([export_column_label(field) for field in fields])
            for session in sessions:
                writer.writerow([export_value(session, field, notes_getter) for field in fields])


def _xlsx_cell(reference: str, value: str, style: int = 0) -> str:
    escaped = escape(value)
    preserve = ' xml:space="preserve"' if value[:1].isspace() or value[-1:].isspace() else ""
    style_attr = f' s="{style}"' if style else ""
    return f'<c r="{reference}" t="inlineStr"{style_attr}><is><t{preserve}>{escaped}</t></is></c>'


def _column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _xlsx_sheet(groups: list[ExportGroup], fields: list[str], notes_getter) -> str:
    rows: list[str] = []
    merges: list[str] = []
    row_number = 1
    field_count = len(fields)
    for group_index, (folder_key, sessions) in enumerate(groups):
        title = folder_export_title(folder_key)
        rows.append(f'<row r="{row_number}" ht="24" customHeight="1">' + _xlsx_cell(f"A{row_number}", title, 1) + "</row>")
        if field_count > 1:
            merges.append(f"A{row_number}:{_column_name(field_count)}{row_number}")
        row_number += 1
        header_cells = "".join(
            _xlsx_cell(f"{_column_name(column)}{row_number}", export_column_label(field), 2)
            for column, field in enumerate(fields, start=1)
        )
        rows.append(f'<row r="{row_number}">{header_cells}</row>')
        row_number += 1
        for session in sessions:
            cells = "".join(
                _xlsx_cell(f"{_column_name(column)}{row_number}", export_value(session, field, notes_getter))
                for column, field in enumerate(fields, start=1)
            )
            rows.append(f'<row r="{row_number}">{cells}</row>')
            row_number += 1
        if group_index < len(groups) - 1:
            row_number += 1

    columns = "".join(
        f'<col min="{index}" max="{index}" width="{max(14, len(export_column_label(field)) + 2)}" customWidth="1"/>'
        for index, field in enumerate(fields, start=1)
    )
    merge_xml = f'<mergeCells count="{len(merges)}">' + "".join(f'<mergeCell ref="{ref}"/>' for ref in merges) + "</mergeCells>" if merges else ""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetViews><sheetView workbookViewId="0" showGridLines="0"/></sheetViews>'
        f'<cols>{columns}</cols><sheetData>{"".join(rows)}</sheetData>{merge_xml}</worksheet>'
    )


def write_xlsx_export(path: str | Path, groups: list[ExportGroup], fields: list[str], notes_getter) -> None:
    """Write a compact, dependency-free XLSX workbook with one table per folder."""
    content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>'''
    root_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'''
    workbook = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Verbindungen" sheetId="1" r:id="rId1"/></sheets></workbook>'''
    workbook_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'''
    styles = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF1F4E78"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0"><alignment horizontal="left"/></xf></cellXfs></styleSheet>'''
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/styles.xml", styles)
        archive.writestr("xl/worksheets/sheet1.xml", _xlsx_sheet(groups, fields, notes_getter))
