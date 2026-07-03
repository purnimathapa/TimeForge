"""
timetable/exports.py

In-memory PDF and Excel generation for timetable grids.
"""

from __future__ import annotations

from collections import defaultdict
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# reportlab is already locked in requirements.txt for timetable PDFs because it
# is pure Python and avoids the system Cairo/Pango dependencies of weasyprint.
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


DAY_NAMES = {
    1: "Monday",
    2: "Tuesday",
    3: "Wednesday",
    4: "Thursday",
    5: "Friday",
}


def _grid_data(slots, timeslots):
    days = sorted({ts.day_of_week for ts in timeslots})
    periods = sorted({ts.period_number for ts in timeslots})
    period_times = {}
    for ts in timeslots:
        period_times.setdefault(ts.period_number, (ts.start_time, ts.end_time))

    grid = defaultdict(list)
    for slot in slots:
        grid[(slot.timeslot.day_of_week, slot.timeslot.period_number)].append(slot)

    return days, periods, period_times, grid


def _slot_lines(slot, scope):
    lines = [slot.class_session.subject.code]
    if scope != "teacher" and slot.teacher:
        lines.append(slot.teacher.user.get_full_name() or slot.teacher.user.username)
    if scope != "room":
        lines.append(slot.room.name)
    if scope != "section":
        lines.append(slot.class_session.section.name)
    if slot.is_locked:
        lines.append("Locked")
    return lines


def _cell_text(slots, scope):
    if not slots:
        return ""
    return "\n\n".join("\n".join(_slot_lines(slot, scope)) for slot in slots)


def export_timetable_pdf(*, slots, timeslots, title, subtitle, scope):
    """Return PDF bytes for a timetable grid."""
    days, periods, period_times, grid = _grid_data(slots, timeslots)
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        rightMargin=0.35 * inch,
        leftMargin=0.35 * inch,
        topMargin=0.35 * inch,
        bottomMargin=0.35 * inch,
    )

    styles = getSampleStyleSheet()
    story = [
        Paragraph(title, styles["Title"]),
        Paragraph(subtitle, styles["Normal"]),
        Spacer(1, 0.18 * inch),
    ]

    table_data = [["Period"] + [DAY_NAMES.get(day, f"Day {day}") for day in days]]
    for period in periods:
        start_time, end_time = period_times[period]
        row = [f"P{period}\n{start_time:%H:%M}-{end_time:%H:%M}"]
        for day in days:
            row.append(_cell_text(grid[(day, period)], scope))
        table_data.append(row)

    available_width = 10.3 * inch
    period_width = 0.9 * inch
    day_width = (available_width - period_width) / max(len(days), 1)
    table = Table(
        table_data,
        colWidths=[period_width] + [day_width for _ in days],
        repeatRows=1,
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#343a40")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#f1f3f5")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#adb5bd")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("ALIGN", (0, 1), (0, -1), "CENTER"),
        ("LEADING", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (1, 1), (-1, -1), [colors.white, colors.HexColor("#fbfcfd")]),
    ]))
    story.append(table)
    doc.build(story)
    return buffer.getvalue()


def export_timetable_xlsx(*, slots, timeslots, title, subtitle, scope):
    """Return XLSX bytes for a timetable grid."""
    days, periods, period_times, grid = _grid_data(slots, timeslots)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Timetable"

    max_col = len(days) + 1
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max_col)
    sheet.merge_cells(start_row=2, start_column=1, end_row=2, end_column=max_col)
    sheet.cell(1, 1, title)
    sheet.cell(2, 1, subtitle)
    sheet.cell(1, 1).font = Font(size=16, bold=True, color="1F2937")
    sheet.cell(2, 1).font = Font(size=10, color="6C757D")

    header_fill = PatternFill("solid", fgColor="343A40")
    period_fill = PatternFill("solid", fgColor="F1F3F5")
    thin = Side(style="thin", color="ADB5BD")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    header_row = 4
    sheet.cell(header_row, 1, "Period")
    for index, day in enumerate(days, start=2):
        sheet.cell(header_row, index, DAY_NAMES.get(day, f"Day {day}"))

    for cell in sheet[header_row]:
        cell.fill = header_fill
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = border

    for row_index, period in enumerate(periods, start=header_row + 1):
        start_time, end_time = period_times[period]
        label = f"P{period}\n{start_time:%H:%M}-{end_time:%H:%M}"
        period_cell = sheet.cell(row_index, 1, label)
        period_cell.fill = period_fill
        period_cell.font = Font(bold=True)
        period_cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        period_cell.border = border

        for col_index, day in enumerate(days, start=2):
            cell = sheet.cell(row_index, col_index, _cell_text(grid[(day, period)], scope))
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = border

    sheet.freeze_panes = "B5"
    sheet.column_dimensions["A"].width = 14
    for col_index in range(2, max_col + 1):
        sheet.column_dimensions[get_column_letter(col_index)].width = 26
    for row_index in range(header_row + 1, header_row + len(periods) + 1):
        sheet.row_dimensions[row_index].height = 62

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
