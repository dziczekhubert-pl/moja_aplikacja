# -*- coding: utf-8 -*-
import json
import calendar
import io
from pathlib import Path

from django.conf import settings
from django.http import FileResponse

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# --- czcionka z absolutnej ścieżki (działa na Render i lokalnie) ---
FONT_PATH = settings.BASE_DIR / "fonts" / "DejaVuSans.ttf"
pdfmetrics.registerFont(TTFont("DejaVuSans", str(FONT_PATH)))


def _load_table_from_file(file_name: str):
    """Wczytuje JSON z BASE_DIR/file_name."""
    path = settings.BASE_DIR / file_name
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _create_title_table(month, year, col_widths, body_style):
    title = Table([[Paragraph(f"{month} {year}", body_style)]], colWidths=[sum(col_widths)])
    title.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    return title


def generate_pdf_response(file_name: str) -> FileResponse:
    """
    Główna funkcja wywoływana z widoku Django.
    Wczytuje dane z JSON (BASE_DIR/file_name), buduje PDF w pamięci i zwraca FileResponse.
    """
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

    # style
    styles = getSampleStyleSheet()
    for st in styles.byName:
        styles[st].fontName = "DejaVuSans"
    body_style = ParagraphStyle(name="BodySmaller", fontName="DejaVuSans", fontSize=6, leading=8, alignment=TA_CENTER)
    day_style = ParagraphStyle(name="DayNoWrap", parent=body_style, wordWrap="CJK")

    headers_fixed = ["Lp.", "Nazwisko i imię", "Xz", "Wz", "Nd"]
    headers_days = [str(d) for d in range(1, days_in_month + 1)]
    headers_end = ["Wyk.\nXz", "Wyk.\nWz/W"]
    header_paragraphs = [Paragraph(h, body_style) for h in headers_fixed] \
                        + [Paragraph(hd, day_style) for hd in headers_days] \
                        + [Paragraph(h, body_style) for h in headers_end]

    holidays = {"01-01", "06-01", "21-04", "01-05", "03-05", "19-06",
                "15-08", "01-11", "11-11", "25-12", "26-12"}

    # szerokości kolumn
    lp_w, name_w = 0.6*cm, 3.5*cm
    xz_w = wz_w = nd_w = 0.6*cm
    day_w, wyk_xz_w, wyk_wz_w = 0.7*cm, 0.8*cm, 0.8*cm
    col_widths = [lp_w, name_w, xz_w, wz_w, nd_w] + [day_w]*days_in_month + [wyk_xz_w, wyk_wz_w]

    def create_subtable(start_idx, end_idx, lp_start):
        table_matrix = [header_paragraphs]
        items = list(data.items())
        actual_rows = end_idx - start_idx

        for row_num in range(start_idx, end_idx):
            lp_val = lp_start + (row_num - start_idx)
            user, values = (items[row_num] if row_num < len(items) else ("", []))

            row_top, row_bottom = [], []
            # Lp, Nazwisko, Xz, Wz, Nd (rowspan)
            for content in (str(lp_val), user, "", "", ""):
                row_top.append(Paragraph(content, body_style))
                row_bottom.append(Paragraph("", body_style))
            # dni
            for d_idx in range(days_in_month):
                val = values[d_idx] if d_idx < len(values) else ""
                row_top.append(Paragraph(val, day_style))
                row_bottom.append(Paragraph("", day_style))
            # Wyk.Xz / Wyk.Wz
            row_top.append(Paragraph("", body_style)); row_bottom.append(Paragraph("", body_style))
            row_top.append(Paragraph("", body_style)); row_bottom.append(Paragraph("", body_style))

            table_matrix += [row_top, row_bottom]

        # dopełnienie do 20 wierszy logicznych
        rows_created = actual_rows * 2
        target = 20 * 2
        while rows_created < target:
            lp_val = str(lp_start + actual_rows + (rows_created // 2))
            row_top = [Paragraph(lp_val, body_style),
                       Paragraph("", body_style),
                       Paragraph("", body_style),
                       Paragraph("", body_style),
                       Paragraph("", body_style)]
            row_top += [Paragraph("", day_style) for _ in range(days_in_month)]
            row_top += [Paragraph("", body_style), Paragraph("", body_style)]
            row_bottom = [Paragraph("", body_style) for _ in row_top]
            table_matrix += [row_top, row_bottom]
            rows_created += 2

        footer = Paragraph("Nd - ilość przepracowanych niedziel lub świąt w poprzednim miesiącu", body_style)
        table_matrix.append([footer] + [""] * (len(col_widths) - 1))
        return table_matrix

    def style_subtable(tbl):
        cmds = [
            ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BACKGROUND', (0, 0), (-1, 0), colors.white),
            ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('VALIGN', (0, 1), (-1, -2), 'TOP'),
            ('BACKGROUND', (2, 0), (2, 0), colors.lightgrey),  # Xz
            ('BACKGROUND', (3, 0), (3, 0), colors.lightgrey),  # Wz
            ('BACKGROUND', (4, 0), (4, 0), colors.yellow),     # Nd
            ('LEFTPADDING', (0, 0), (-1, -1), 1),
            ('RIGHTPADDING', (0, 0), (-1, -1), 1),
            ('TOPPADDING', (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
            ('BACKGROUND', (0, 1), (0, -2), colors.white),
            ('BACKGROUND', (1, 1), (1, -2), colors.white),
            ('ALIGN', (1, 1), (1, -2), 'LEFT'),
            ('SPAN', (0, -1), (-1, -1)),
            ('BACKGROUND', (0, -1), (-1, -1), colors.white),
            ('BOX', (0, -1), (-1, -1), 0.5, colors.black),
            ('ALIGN', (0, -1), (-1, -1), 'LEFT'),
            ('VALIGN', (0, -1), (-1, -1), 'MIDDLE'),
        ]
        col_wyk_xz = 5 + days_in_month
        col_wyk_wz = 6 + days_in_month

        total = tbl._nrows
        for r in range(1, total - 1, 2):
            if r + 1 >= total - 1: break
            cmds += [
                ('SPAN', (0, r), (0, r + 1)),
                ('SPAN', (1, r), (1, r + 1)),
                ('SPAN', (2, r), (2, r + 1)),
                ('SPAN', (3, r), (3, r + 1)),
                ('SPAN', (4, r), (4, r + 1)),
                ('SPAN', (col_wyk_xz, r), (col_wyk_xz, r + 1)),
                ('SPAN', (col_wyk_wz, r), (col_wyk_wz, r + 1)),
            ]

        for col in range(5, 5 + days_in_month):
            day = col - 4
            try:
                wd = calendar.weekday(int(year), month_number, day)
            except Exception:
                wd = -1
            key = f"{day:02d}-{month_number:02d}"
            if key in holidays or wd == 6:
                color = colors.red
            elif wd == 5:
                color = colors.green
            else:
                color = colors.white
            cmds.append(('BACKGROUND', (col, 0), (col, -2), color))

        cmds += [
            ('BACKGROUND', (col_wyk_xz, 1), (col_wyk_xz, -2), colors.lightgrey),
            ('BACKGROUND', (col_wyk_wz, 1), (col_wyk_wz, -2), colors.lightgrey),
        ]
        tbl.setStyle(TableStyle(cmds))

    # --- budowa PDF w pamięci ---
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=0.3 * cm, rightMargin=0.3 * cm,
        topMargin=0.3 * cm, bottomMargin=0.3 * cm,
    )

    story = []
    num_rows = len(data)
    chunk = 20
    start = 0
    lp_start = 1

    while start < num_rows or start == 0:
        end = min(start + chunk, num_rows)
        title = _create_title_table(month, year, col_widths, body_style)
        story.append(title)

        matrix = create_subtable(start, end, lp_start)
        nrows = len(matrix)
        row_heights = [0.6 * cm] + [0.35 * cm] * (nrows - 2) + [0.5 * cm]
        table = Table(matrix, colWidths=col_widths, rowHeights=row_heights, repeatRows=1)
        style_subtable(table)
        story.append(table)

        start += chunk
        lp_start += chunk
        if start < num_rows:
            story.append(PageBreak())

    doc.build(story)
    buffer.seek(0)

    filename = f"grafik_{group.replace(' ', '_')}_{month}_{year}.pdf"
    return FileResponse(buffer, as_attachment=True, filename=filename)
