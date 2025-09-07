# pierwsza_app/core/pdf_karty.py
# ...
import io
import json
from pathlib import Path
from django.conf import settings
from django.http import FileResponse

# jeśli masz już zdefiniowane czcionki/styl – zostaw
# (FONT_PATH, rejestracja DejaVuSans itd.)

def _load_table_from_file(file_name: str):
    path = settings.BASE_DIR / file_name
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def generate_karty_pdf_response(file_name: str) -> FileResponse:
    """
    1) Próbuje użyć starego generatora (RozliczKarty3.save_tables_to_pdf) → identyczny wygląd (WeasyPrint).
    2) Jeśli się nie uda (WeasyPrint/moduł niedostępny) → fallback ReportLab (działające pobranie).
    """
    json_path = settings.BASE_DIR / file_name
    table_data = _load_table_from_file(file_name)

    group = table_data.get("group", "Nieznana_grupa")
    month = table_data.get("month", "Nieznany_miesiąc")
    year  = table_data.get("year", "Nieznany_rok")

    # --- ścieżka domyślnego pliku wg starej konwencji ---
    expected_pdf = json_path.parent / f"karta_{group}_{month}_{year}.pdf"

    # --- ścieżka 1: spróbuj uruchomić stary generator (WeasyPrint) ---
    try:
        from RozliczKarty3 import save_tables_to_pdf as _save_old  # stara funkcja
        _save_old(str(json_path), table_data)  # generuje PDF obok JSON
        # jeśli nazwa inna, weź pierwszy karta_*.pdf
        if expected_pdf.exists():
            pdf_path = expected_pdf
        else:
            candidates = sorted(json_path.parent.glob("karta_*.pdf"))
            if not candidates:
                raise FileNotFoundError("Stary generator nie zapisał pliku PDF.")
            pdf_path = candidates[0]

        # zwróć dokładnie ten plik (stary wygląd)
        return FileResponse(open(pdf_path, "rb"), as_attachment=True, filename=pdf_path.name)

    except Exception:
        # brak WeasyPrint/modułu – przejdź do fallbacku ReportLab
        pass

    # --- ścieżka 2: fallback ReportLab (działa bez WeasyPrint) ---
    # Uwaga: to może minimalnie różnić się wyglądem.
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    # czcionka (jak w grafiku)
    FONT_PATH = settings.BASE_DIR / "fonts" / "DejaVuSans.ttf"
    if Path(FONT_PATH).exists():
        try:
            pdfmetrics.registerFont(TTFont("DejaVuSans", str(FONT_PATH)))
        except Exception:
            pass

    # style
    styles = getSampleStyleSheet()
    for st in styles.byName:
        styles[st].fontName = "DejaVuSans"

    title_style = ParagraphStyle(name="Title", parent=styles["Heading2"], alignment=TA_CENTER, leading=14, spaceAfter=4)
    head_style  = ParagraphStyle(name="Head",  parent=styles["Normal"],   fontSize=8, alignment=TA_CENTER, leading=10)
    cell_left   = ParagraphStyle(name="CellL", parent=styles["Normal"],   fontSize=8, alignment=TA_LEFT,  leading=10)
    cell_center = ParagraphStyle(name="CellC", parent=styles["Normal"],   fontSize=8, alignment=TA_CENTER,leading=10)
    note_style  = ParagraphStyle(name="Note",  parent=styles["Normal"],   fontSize=7, alignment=TA_LEFT,  leading=9)

    # dane → wiersze
    def normalize(data):
        rows = []
        if isinstance(data, dict):
            for name, values in data.items():
                if isinstance(values, dict):
                    xz = str(values.get("xz", "") or "")
                    wz = str(values.get("wz", "") or "")
                    nd = str(values.get("nd", "") or "")
                    note = str(values.get("note", "") or values.get("uwagi", "") or "")
                else:
                    xz = str(values[0]) if isinstance(values, (list, tuple)) and len(values) > 0 else ""
                    wz = str(values[1]) if isinstance(values, (list, tuple)) and len(values) > 1 else ""
                    nd = str(values[2]) if isinstance(values, (list, tuple)) and len(values) > 2 else ""
                    note = str(values[3]) if isinstance(values, (list, tuple)) and len(values) > 3 else ""
                rows.append((str(name), xz, wz, nd, note))
        elif isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                name = item.get("name") or item.get("nazwisko") or item.get("pracownik") or ""
                xz = str(item.get("xz", "") or "")
                wz = str(item.get("wz", "") or "")
                nd = str(item.get("nd", "") or "")
                note = str(item.get("note", "") or item.get("uwagi", "") or "")
                rows.append((str(name), xz, wz, nd, note))
        return rows

    rows = normalize(table_data.get("data", {}))

    # układ zbliżony do starego: Lp | Nazwisko i imię | Xz | Wz | Nd | Uwagi
    col_widths = [0.8*cm, 6.5*cm, 1.5*cm, 1.5*cm, 1.5*cm, 11.4*cm]
    headers = ["Lp.", "Nazwisko i imię", "Xz", "Wz", "Nd", "Uwagi"]
    header_pars = [Paragraph(h, head_style) for h in headers]

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=0.3*cm, rightMargin=0.3*cm,
        topMargin=0.3*cm, bottomMargin=0.3*cm,
    )

    story = []
    chunk = 25
    start = 0
    lp_start = 1
    while start < len(rows) or start == 0:
        end = min(start + chunk, len(rows))
        # tytuł
        total_w = sum(col_widths)
        title_tbl = Table([[Paragraph(f"Karty: {group} — {month} {year}", head_style)]], colWidths=[total_w])
        title_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ]))
        story.append(title_tbl)

        matrix = [header_pars]
        page_rows = rows[start:end]
        for i, (name, xz, wz, nd, note) in enumerate(page_rows, start=lp_start):
            matrix.append([
                Paragraph(str(i), cell_center),
                Paragraph(name, cell_left),
                Paragraph(xz, cell_center),
                Paragraph(wz, cell_center),
                Paragraph(nd, cell_center),
                Paragraph(note, cell_left),
            ])
        # dopełnij do stałej liczby wierszy
        while len(matrix) - 1 < chunk:
            i = lp_start + (len(matrix) - 1)
            matrix.append([
                Paragraph(str(i), cell_center),
                Paragraph("", cell_left),
                Paragraph("", cell_center),
                Paragraph("", cell_center),
                Paragraph("", cell_center),
                Paragraph("", cell_left),
            ])

        # stopka
        footer = Paragraph(
            "Nd — liczba przepracowanych niedziel/świąt w poprzednim miesiącu. Xz/Wz zgodnie z regulaminem.",
            note_style,
        )
        matrix.append([footer] + [Paragraph("", cell_left)]*(len(col_widths)-1))

        nrows = len(matrix)
        row_heights = [0.6*cm] + [0.38*cm]*(nrows - 2) + [0.5*cm]

        tbl = Table(matrix, colWidths=col_widths, rowHeights=row_heights, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
            ("INNERGRID", (0, 0), (-1, -2), 0.25, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("VALIGN", (0, 1), (-1, -2), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("SPAN", (0, -1), (-1, -1)),
            ("BACKGROUND", (0, -1), (-1, -1), colors.white),
            ("BOX", (0, -1), (-1, -1), 0.5, colors.black),
        ]))
        story.append(tbl)

        start += chunk
        lp_start += chunk
        if start < len(rows):
            story.append(PageBreak())

    doc.build(story)
    buffer.seek(0)

    filename = f"karta_{str(group).replace(' ', '_')}_{month}_{year}.pdf"
    return FileResponse(buffer, as_attachment=True, filename=filename)
