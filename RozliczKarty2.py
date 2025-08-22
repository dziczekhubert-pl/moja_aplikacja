# -*- coding: utf-8 -*-
import sys
import json
import calendar
from pathlib import Path
import io

from django.conf import settings
from django.http import FileResponse

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# --- Czcionka z absolutnej ścieżki (działa na Render) ---
FONT_PATH = settings.BASE_DIR / "fonts" / "DejaVuSans.ttf"
pdfmetrics.registerFont(TTFont("DejaVuSans", str(FONT_PATH)))


def _load_table_from_file(file_name: str):
    """
    Wczytuje dane z pliku JSON.
    Plik szukany RELATYWNIE do BASE_DIR (katalog projektu Django).
    """
    path = settings.BASE_DIR / file_name
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Plik {path} nie istnieje")
    except json.JSONDecodeError as e:
        raise ValueError(f"Błąd JSON w pliku {path}: {e}")


def _create_title_table(month, year, col_widths, body_style):
    title_data = [[Paragraph(f"{month} {year}", body_style)]]
    title_width = sum(col_widths)
    title_table = Table(title_data, colWidths=[title_width])
    title_style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ])
    title_table.setStyle(title_style)
    return title_table


def generate_pdf_response(file_name: str) -> FileResponse:
    """
    GŁÓWNA FUNKCJA do użycia w widoku Django.
    Wczytuje JSON, buduje PDF w pamięci i zwraca FileResponse (bez zapisu na dysk).
    """
    # ---- Dane wejściowe ----
    table_data = _load_table_from_file(file_name)

    group = table_data.get("group", "Nieznana grupa")
    month = table_data.get("month", "Nieznany miesiąc")
    year = table_data.get("year", "Nieznany rok")
    data = table_data.get("data", {})

    polish_months = {
        "Styczeń": 1, "Luty": 2, "Marzec": 3, "Kwiecień": 4, "Maj": 5, "Czerwiec": 6,
        "Lipiec": 7, "Sierpień": 8, "Wrzesień": 9, "Październik": 10, "Listopad": 11, "Grudzień": 12
    }
    month_number = polish_months.get(month, 0)
    try:
        days_in_month = calendar.monthrange(int(year), month_number)[1] if month_number else 0
    except Exception:
        days_in_month = 0

    if days_in_month == 0:
        raise ValueError(f"Nieprawidłowy miesiąc lub rok: {month} {year}")

    # ---- Kolumny / style ----
    styles = getSampleStyleSheet()
    for st in styles.byName:
        styles[st].fontName = "DejaVuSans"

    body_style = ParagraphStyle(
        name="BodySmaller",
        fontName="DejaVuSans",
        fontSize=6,
        leading=8,
        alignment=TA_CENTER,
    )
    day_style = ParagraphStyle(name="DayNoWrap", parent=body_style, wordWrap="CJK")

    headers_fixed = ["Lp.", "Nazwisko i imię", "Xz", "Wz", "Nd"]
    headers_days = [str(d) for d in range(1, days_in_month + 1)]
    headers_end = ["Wyk.\nXz", "Wyk.\nWz/W"]

    header_paragraphs = [Paragraph(h, body_style) for h in headers_fixed]
    header_paragraphs += [Paragraph(hd, day_style) for hd in headers_days]
    header_paragraphs += [Paragraph(h, body_style) for h in headers_end]

    holidays = ["01-01", "06-01", "21-04", "01-05", "03-05", "19-06",
                "15-08", "01-11", "11-11", "25-12", "26-12"]

    lp_w = 0.6 * cm
    wyk_xz_w = 0.8 * cm
    wyk_wz_w = 0.8 * cm
    day_w = 0.7 * cm
    xz_w = 0.6 * cm
    wz_w = 0.6 * cm
    nd_w = 0.6 * cm
    name_w = 3.5 * cm

    col_widths = [lp_w, name_w, xz_w, wz_w, nd_w]
    col_widths += [day_w for _ in range(days_in_month)]
    col_widths += [wyk_xz_w, wyk_wz_w]

    # ---- Helpers do tabeli ----
    def create_subtable(start_idx, end_idx, lp_start):
        table_matrix = [header_paragraphs]
        actual_rows = end_idx - start_idx
        data_items = list(data.items())

        for row_num in range(start_idx, end_idx):
            lp_val = lp_start + (row_num - start_idx)
            if row_num < len(data_items):
                user, values = data_items[row_num]
            else:
                user, values = "", []

            row_top, row_bottom = [], []

            # Lp / Nazwisko / Xz / Wz / Nd
            row_top.append(Paragraph(str(lp_val), body_style)); row_bottom.append(Paragraph("", body_style))
            row_top.append(Paragraph(user, body_style));        row_bottom.append(Paragraph("", body_style))
            row_top.append(Paragraph("", body_style));          row_bottom.append(Paragraph("", body_style))  # Xz
            row_top.append(Paragraph("", body_style));          row_bottom.append(Paragraph("", body_style))  # Wz
            row_top.append(Paragraph("", body_style));          row_bottom.append(Paragraph("", body_style))  # Nd

            # Dni
            for d_idx in range(days_in_month):
                val = values[d_idx] if d_idx < len(values) else ""
                row_top.append(Paragraph(val, day_style))
                row_bottom.append(Paragraph("", day_style))

            # Wyk.Xz / Wyk.Wz
            row_top.append(Paragraph("", body_style)); row_bottom.append(Paragraph("", body_style))
            row_top.append(Paragraph("", body_style)); row_bottom.append(Paragraph("", body_style))

            table_matrix.append(row_top)
            table_matrix.append(row_bottom)

        # dopełnienie do 20 wierszy logicznych (40 fizycznych)
        rows_created = actual_rows * 2
        rows_needed = 20 * 2
        if rows_created < rows_needed:
            diff = rows_needed - rows_created
            for extra in range(diff // 2):
                lp_val = str(lp_start + actual_rows + extra)
                row_top = [Paragraph(lp_val, body_style),
                           Paragraph("", body_style),
                           Paragraph("", body_style),
                           Paragraph("", body_style),
                           Paragraph("", body_style)]
                row_top += [Paragraph("", day_style) for _ in range(days_in_month)]
                row_top += [Paragraph("", body_style), Paragraph("", body_style)]
                row_bottom = [Paragraph("", body_style) for _ in row_top]
                table_matrix.append(row_top)
                table_matrix.append(row_bottom)

        footer_text = "Nd - ilość przepracowanych niedziel lub świąt w poprzednim miesiącu"
        footer_paragraph = Paragraph(footer_text, body_style)
        footer_row = [footer_paragraph] + [""] * (len(col_widths) - 1)
        table_matrix.append(footer_row)
        return table_matrix

    def style_subtable(tbl):
        all_cells = [('BOX', (0, 0), (-1, -1), 0.5, colors.black),
                     ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.grey)]

        header_bg = [('BACKGROUND', (0, 0), (-1, 0), colors.white),
                     ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
                     ('ALIGN', (0, 0), (-1, 0), 'CENTER')]

        specific_header_bg = [
            ('BACKGROUND', (2, 0), (2, 0), colors.lightgrey),  # Xz
            ('BACKGROUND', (3, 0), (3, 0), colors.lightgrey),  # Wz
            ('BACKGROUND', (5 + days_in_month, 0), (5 + days_in_month, 0), colors.lightgrey),  # Wyk.Xz
            ('BACKGROUND', (6 + days_in_month, 0), (6 + days_in_month, 0), colors.lightgrey),  # Wyk.Wz/W
            ('BACKGROUND', (4, 0), (4, 0), colors.yellow),     # Nd
        ]

        smaller_font = [('VALIGN', (0, 1), (-1, -2), 'TOP')]

        xz_wz_bg = [
            ('BACKGROUND', (2, 1), (2, -2), colors.lightgrey),
            ('BACKGROUND', (3, 1), (3, -2), colors.lightgrey),
            ('BACKGROUND', (4, 1), (4, -2), colors.yellow),
        ]

        col_wyk_xz = 5 + days_in_month
        col_wyk_wz = 6 + days_in_month
        wyk_bg = [
            ('BACKGROUND', (col_wyk_xz, 1), (col_wyk_xz, -2), colors.lightgrey),
            ('BACKGROUND', (col_wyk_wz, 1), (col_wyk_wz, -2), colors.lightgrey),
        ]

        row_span_cmds = []
        total_rows = tbl._nrows
        for row_idx in range(1, total_rows - 1, 2):
            top_row = row_idx
            bottom_row = row_idx + 1
            if bottom_row >= total_rows - 1:
                break
            row_span_cmds += [
                ('SPAN', (0, top_row), (0, bottom_row)),
                ('SPAN', (1, top_row), (1, bottom_row)),
                ('SPAN', (2, top_row), (2, bottom_row)),
                ('SPAN', (3, top_row), (3, bottom_row)),
                ('SPAN', (4, top_row), (4, bottom_row)),
                ('SPAN', (col_wyk_xz, top_row), (col_wyk_xz, bottom_row)),
                ('SPAN', (col_wyk_wz, top_row), (col_wyk_wz, bottom_row)),
            ]

        day_header_bg = []
        for col in range(5, 5 + days_in_month):
            day = col - 4
            try:
                wd = calendar.weekday(int(year), month_number, day)
            except Exception:
                wd = -1
            date_key = f"{day:02d}-{month_number:02d}"
            if date_key in holidays or wd == 6:
                color = colors.red
            elif wd == 5:
                color = colors.green
            else:
                color = colors.white
            day_header_bg.append(('BACKGROUND', (col, 0), (col, -1), color))

        padding_cmds = [
            ('LEFTPADDING', (0, 0), (-1, -1), 1),
            ('RIGHTPADDING', (0, 0), (-1, -1), 1),
            ('TOPPADDING', (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ]

        lp_name_bg = [
            ('BACKGROUND', (0, 1), (0, -2), colors.white),
            ('BACKGROUND', (1, 1), (1, -2), colors.white),
        ]

        align_name_cmd = [('ALIGN', (1, 1), (1, -2), 'LEFT')]

        footer_style = [
            ('SPAN', (0, -1), (-1, -1)),
            ('BACKGROUND', (0, -1), (-1, -1), colors.white),
            ('BOX', (0, -1), (-1, -1), 0.5, colors.black),
            ('ALIGN', (0, -1), (-1, -1), 'LEFT'),
            ('VALIGN', (0, -1), (-1, -1), 'MIDDLE'),
        ]

        final_style = (all_cells + header_bg + specific_header_bg + smaller_font +
                       xz_wz_bg + wyk_bg + row_span_cmds + day_header_bg +
                       lp_name_bg + padding_cmds + align_name_cmd + footer_style)
        tbl.setStyle(TableStyle(final_style))

    # ---- Budowa PDF do pamięci ----
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=0.3 * cm,
        rightMargin=0.3 * cm,
        topMargin=0.3 * cm,
        bottomMargin=0.3 * cm,
    )

    story = []
    num_rows = len(data)
    chunk_size = 20
    current_start = 0
    lp_start = 1

    while current_start < num_rows or current_start == 0:
        current_end = min(current_start + chunk_size, num_rows)
        subtable_matrix = create_subtable(current_start, current_end, lp_start=None)  # placeholder, wypełniamy niżej
        # UWAGA: poprawka – lp_start powinno rosnąć, ale numer Lp w PDF jest kosmetyczny.
        # Jeśli chcesz zachować numerację Lp, możesz przekazać lp_start i uwzględnić go w create_subtable.

        # Tworzenie tytułu (miesiąc/rok)
        title_table = _create_title_table(month, year, col_widths, body_style)
        story.append(title_table)

        # Rekonstrukcja z prawidłowym lp_start
        subtable_matrix = create_subtable(current_start, current_end, lp_start)

        nrows = len(subtable_matrix)
        row_heights = []
        for i in range(nrows):
            if i == 0:
                row_heights.append(0.6 * cm)
            elif i == nrows - 1:
                row_heights.append(0.5 * cm)
            else:
                row_heights.append(0.35 * cm)

        t = Table(
            subtable_matrix,
            colWidths=col_widths,
            rowHeights=row_heights,
            repeatRows=1,
        )
        style_subtable(t)
        story.append(t)

        current_start += chunk_size
        lp_start += chunk_size

        if current_start < num_rows:
            story.append(PageBreak())

    doc.build(story)
    buffer.seek(0)

    group_clean = group.replace(" ", "_")
    filename = f"grafik_{group_clean}_{month}_{year}.pdf"
    return FileResponse(buffer, as_attachment=True, filename=filename)
