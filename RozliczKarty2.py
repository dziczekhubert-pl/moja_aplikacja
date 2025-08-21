# -*- coding: utf-8 -*-
import sys
import os
import json
import calendar
import platform

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
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Rejestrujemy czcionkę DejaVuSans (zawierającą polskie znaki)
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
FONT_PATH = BASE_DIR / "fonts" / "DejaVuSans.ttf"

pdfmetrics.registerFont(TTFont('DejaVuSans', str(FONT_PATH)))


def load_table_from_file(file_name):
    """
    Funkcja do wczytywania danych z pliku JSON.
    """
    try:
        with open(file_name, "r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        print(f"Plik {file_name} nie istnieje!")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Błąd w formacie JSON w pliku {file_name}!")
        sys.exit(1)


def create_title_table(month, year, col_widths, body_style):
    """
    Tworzy tabelę z nagłówkiem zawierającym miesiąc i rok oraz cienką linią poniżej.
    """
    title_data = [[Paragraph(f"{month} {year}", body_style)]]
    title_width = sum(col_widths)
    title_table = Table(title_data, colWidths=[title_width])

    # Styl dla tabeli-nagłówka z BIAŁYM tłem oraz cienką linią poniżej
    title_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.white),
        # Grubość linii ustawiona na 0.5
        ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
        ('LINEBELOW', (0, 0), (-1, 0), 0.5, colors.black),  # Cienka linia poniżej
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ])
    title_table.setStyle(title_style)

    return title_table


def generate_pdf(file_name):
    """
    Generuje plik PDF (A4 w poziomie), tak aby tabela mieściła się na stronie.
    """
    # Wczytanie danych
    table_data = load_table_from_file(file_name)

    group = table_data.get("group", "Nieznana grupa")
    month = table_data.get("month", "Nieznany miesiąc")
    year = table_data.get("year", "Nieznany rok")
    data = table_data.get("data", {})

    # Ustalenie liczby dni w miesiącu
    polish_months = {
        "Styczeń": 1, "Luty": 2, "Marzec": 3, "Kwiecień": 4, "Maj": 5, "Czerwiec": 6,
        "Lipiec": 7, "Sierpień": 8, "Wrzesień": 9, "Październik": 10, "Listopad": 11, "Grudzień": 12
    }
    month_number = polish_months.get(month, 0)
    try:
        days_in_month = calendar.monthrange(int(year), month_number)[
            1] if month_number else 0
    except:
        days_in_month = 0

    if days_in_month == 0:
        print(f"Nieprawidłowy miesiąc lub rok: {month} {year}")
        sys.exit(1)

    # Utworzenie nazwy wyjściowego pliku PDF z przedrostkiem "grafik"
    group_clean = group.replace(" ", "_")
    pdf_file_name = f"grafik_{group_clean}_{month}_{year}.pdf"

    # Tworzymy obiekt dokumentu A4 (landscape), zmniejszamy marginesy
    doc = SimpleDocTemplate(
        pdf_file_name,
        pagesize=landscape(A4),
        leftMargin=0.3*cm,
        rightMargin=0.3*cm,
        topMargin=0.3*cm,
        bottomMargin=0.3*cm
    )

    # Style bazowe
    styles = getSampleStyleSheet()
    for st in styles.byName:
        styles[st].fontName = "DejaVuSans"

    # Zmniejszamy rozmiar czcionki i leading (odstęp między wierszami)
    body_style = ParagraphStyle(
        name="BodySmaller",
        fontName="DejaVuSans",
        fontSize=6,
        leading=8,
        alignment=TA_CENTER
    )

    day_style = ParagraphStyle(
        name="DayNoWrap",
        parent=body_style,
        wordWrap='CJK'
    )

    # Nagłówki tabeli (wiersz 0)
    headers_fixed = ["Lp.", "Nazwisko i imię", "Xz", "Wz", "Nd"]
    headers_days = [str(day) for day in range(1, days_in_month + 1)]
    headers_end = ["Wyk.\nXz", "Wyk.\nWz/W"]

    header_paragraphs = []
    for h in headers_fixed:
        header_paragraphs.append(Paragraph(h, body_style))
    for hd in headers_days:
        header_paragraphs.append(Paragraph(hd, day_style))
    for h in headers_end:
        header_paragraphs.append(Paragraph(h, body_style))

    # Lista świąt (na potrzeby kolorowania kolumn)
    holidays = [
        "01-01", "06-01", "21-04", "01-05", "03-05", "19-06",
        "15-08", "01-11", "11-11", "25-12", "26-12"
    ]

    # Ustawienie szerokości kolumn (przykładowe wartości)
    lp_w = 0.6 * cm   # Lp
    wyk_xz_w = 0.8 * cm   # Wyk.Xz
    wyk_wz_w = 0.8 * cm   # Wyk.Wz/W
    day_w = 0.7 * cm   # Dni
    xz_w = 0.6 * cm   # Xz
    wz_w = 0.6 * cm   # Wz
    nd_w = 0.6 * cm   # Nd
    name_w = 3.5 * cm   # Nazwisko i imię

    col_widths = [
        lp_w,      # Lp
        name_w,    # Nazwisko i imię
        xz_w,      # Xz
        wz_w,      # Wz
        nd_w
    ]
    for _ in range(days_in_month):
        col_widths.append(day_w)
    col_widths.append(wyk_xz_w)
    col_widths.append(wyk_wz_w)

    def create_subtable(start_idx, end_idx, lp_start):
        """
        Tworzy fragment tabeli o 20 wierszach "logicznych" (każdy ma 2 subwiersze),
        oraz dodaje stopkę z informacją o "Nd".
        """
        table_matrix = []
        table_matrix.append(header_paragraphs)  # nagłówek

        actual_rows = end_idx - start_idx
        data_items = list(data.items())  # [(username, [values...]), ...]

        for row_num in range(start_idx, end_idx):
            lp_val = lp_start + (row_num - start_idx)
            if row_num < len(data_items):
                user, values = data_items[row_num]
            else:
                user, values = "", []

            # Dwa subwiersze
            row_top = []
            row_bottom = []

            # Kolumny 0..4 z rowSpan (Lp, Nazwisko i imię, Xz, Wz, Nd)
            row_top.append(Paragraph(str(lp_val), body_style))  # Lp
            row_bottom.append(Paragraph("", body_style))

            row_top.append(Paragraph(user, body_style)
                           )         # Nazwisko i imię
            row_bottom.append(Paragraph("", body_style))

            row_top.append(Paragraph("", body_style))           # Xz
            row_bottom.append(Paragraph("", body_style))

            row_top.append(Paragraph("", body_style))           # Wz
            row_bottom.append(Paragraph("", body_style))

            row_top.append(Paragraph("", body_style))           # Nd
            row_bottom.append(Paragraph("", body_style))

            # Kolumny dni
            for d_idx in range(days_in_month):
                val = values[d_idx] if d_idx < len(values) else ""
                row_top.append(Paragraph(val, day_style))
                row_bottom.append(Paragraph("", day_style))

            # Ostatnie 2 kolumny (Wyk.Xz, Wyk.Wz) z rowSpan
            row_top.append(Paragraph("", body_style))  # Wyk.Xz
            row_bottom.append(Paragraph("", body_style))

            row_top.append(Paragraph("", body_style))  # Wyk.Wz
            row_bottom.append(Paragraph("", body_style))

            table_matrix.append(row_top)
            table_matrix.append(row_bottom)

        # Uzupełnianie do 20 wierszy logicznych => 40 fizycznych
        rows_created = actual_rows * 2
        rows_needed = 20 * 2
        if rows_created < rows_needed:
            diff = rows_needed - rows_created
            for extra_row in range(diff // 2):
                lp_val = str(lp_start + actual_rows + extra_row)

                row_top = [
                    Paragraph(lp_val, body_style),  # Lp
                    Paragraph("", body_style),       # Nazwisko
                    Paragraph("", body_style),       # Xz
                    Paragraph("", body_style),       # Wz
                    Paragraph("", body_style)        # Nd
                ]
                for _ in range(days_in_month):
                    row_top.append(Paragraph("", day_style))
                row_top.append(Paragraph("", body_style))  # Wyk.Xz
                row_top.append(Paragraph("", body_style))  # Wyk.Wz

                row_bottom = [Paragraph("", body_style) for _ in row_top]
                table_matrix.append(row_top)
                table_matrix.append(row_bottom)

        # Dodanie stopki
        footer_text = "Nd - ilość przepracowanych niedziel lub świąt w poprzednim miesiącu"
        footer_paragraph = Paragraph(footer_text, body_style)
        footer_row = [footer_paragraph] + [""] * (len(col_widths) - 1)
        table_matrix.append(footer_row)

        return table_matrix

    def style_subtable(tbl):
        # 1) Ramka i siatka
        all_cells = [
            ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.grey)
        ]

        # 2) Nagłówek (wiersz 0)
        header_bg = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.white),
            ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ]

        # 2.a) Ustawienie tła dla nagłówków "Xz", "Wz", "Wyk.Xz", "Wyk.Wz/W" oraz "Nd"
        specific_header_bg = []
        if days_in_month >= 0:
            specific_header_bg = [
                ('BACKGROUND', (2, 0), (2, 0), colors.lightgrey),  # "Xz"
                ('BACKGROUND', (3, 0), (3, 0), colors.lightgrey),  # "Wz"
                ('BACKGROUND', (5 + days_in_month, 0),
                 (5 + days_in_month, 0), colors.lightgrey),  # "Wyk.Xz"
                ('BACKGROUND', (6 + days_in_month, 0),
                 (6 + days_in_month, 0), colors.lightgrey),  # "Wyk.Wz/W"
                ('BACKGROUND', (4, 0), (4, 0), colors.yellow),  # "Nd"
            ]

        # 3) Ustawienie pionowego wyśrodkowania wewnątrz wierszy danych
        smaller_font = [
            ('VALIGN', (0, 1), (-1, -2), 'TOP'),
        ]

        # 4) Kolumny Xz, Wz, Nd (zostawiamy poprzedni kolor)
        xz_wz_bg = [
            ('BACKGROUND', (2, 1), (2, -2), colors.lightgrey),  # Xz
            ('BACKGROUND', (3, 1), (3, -2), colors.lightgrey),  # Wz
            ('BACKGROUND', (4, 1), (4, -2), colors.yellow),     # Nd
        ]

        # 5) Kolumny Wyk.Xz i Wyk.Wz/W
        col_wyk_xz = 5 + days_in_month
        col_wyk_wz = 6 + days_in_month
        wyk_bg = [
            ('BACKGROUND', (col_wyk_xz, 1), (col_wyk_xz, -2), colors.lightgrey),
            ('BACKGROUND', (col_wyk_wz, 1), (col_wyk_wz, -2), colors.lightgrey),
        ]

        # 6) Tworzenie rowSpan w odpowiednich kolumnach
        row_span_cmds = []
        total_rows = tbl._nrows
        for row_idx in range(1, total_rows - 1, 2):  # Ostatni wiersz to stopka
            top_row = row_idx
            bottom_row = row_idx + 1
            if bottom_row >= total_rows - 1:
                break
            row_span_cmds.append(
                ('SPAN', (0, top_row), (0, bottom_row)))   # Lp
            row_span_cmds.append(
                ('SPAN', (1, top_row), (1, bottom_row)))   # Nazwisko
            row_span_cmds.append(
                ('SPAN', (2, top_row), (2, bottom_row)))   # Xz
            row_span_cmds.append(
                ('SPAN', (3, top_row), (3, bottom_row)))   # Wz
            row_span_cmds.append(
                ('SPAN', (4, top_row), (4, bottom_row)))   # Nd
            row_span_cmds.append(
                ('SPAN', (col_wyk_xz, top_row), (col_wyk_xz, bottom_row)))  # Wyk.Xz
            row_span_cmds.append(
                ('SPAN', (col_wyk_wz, top_row), (col_wyk_wz, bottom_row)))  # Wyk.Wz/W

        # 7) Kolorowanie całych kolumn dni na podstawie dnia tygodnia i świąt
        day_header_bg = []
        for col in range(5, 5 + days_in_month):
            day = col - 4
            try:
                wd = calendar.weekday(int(year), month_number, day)
            except:
                wd = -1

            date_key = f"{day:02d}-{month_number:02d}"
            if date_key in holidays or wd == 6:    # niedziela lub święto => czerwony
                color = colors.red
            elif wd == 5:                         # sobota => zielony
                color = colors.green
            else:                                 # pozostałe dni => biały
                color = colors.white

            day_header_bg.append(('BACKGROUND', (col, 0), (col, -1), color))

        # 8) Zmniejszenie odstępów (padding) w komórkach
        padding_cmds = [
            ('LEFTPADDING', (0, 0), (-1, -1), 1),
            ('RIGHTPADDING', (0, 0), (-1, -1), 1),
            ('TOPPADDING', (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ]

        # 9) Ustawienie białego tła dla kolumn Lp i Nazwisko i imię (wiersze 1..-2)
        lp_name_bg = [
            ('BACKGROUND', (0, 1), (0, -2), colors.white),  # kolumna Lp
            # kolumna Nazwisko i imię
            ('BACKGROUND', (1, 1), (1, -2), colors.white),
        ]

        # 10) Wyrównanie kolumny "Nazwisko i imię" do lewej (tylko w wierszach danych)
        align_name_cmd = [
            ('ALIGN', (1, 1), (1, -2), 'LEFT'),
        ]

        # 11) Stylizacja stopki
        footer_style = [
            # Rozciągnięcie stopki na wszystkie kolumny
            ('SPAN', (0, -1), (-1, -1)),
            ('BACKGROUND', (0, -1), (-1, -1), colors.white),
            ('BOX', (0, -1), (-1, -1), 0.5, colors.black),
            ('ALIGN', (0, -1), (-1, -1), 'LEFT'),
            ('VALIGN', (0, -1), (-1, -1), 'MIDDLE'),
        ]

        final_style = (
            all_cells +
            header_bg +
            specific_header_bg +
            smaller_font +
            xz_wz_bg +
            wyk_bg +
            row_span_cmds +
            day_header_bg +
            lp_name_bg +
            padding_cmds +
            align_name_cmd +
            footer_style
        )
        tbl.setStyle(TableStyle(final_style))

    story = []

    # Generowanie głównej tabeli (po 20 "logicznych" wierszy)
    num_rows = len(data)
    chunk_size = 20
    current_start = 0
    lp_start = 1

    while current_start < num_rows or current_start == 0:
        current_end = min(current_start + chunk_size, num_rows)
        subtable_matrix = create_subtable(current_start, current_end, lp_start)

        # Tworzenie tabeli z nagłówkiem miesiąc i rok
        title_table = create_title_table(month, year, col_widths, body_style)
        story.append(title_table)

        nrows = len(subtable_matrix)
        # Ustalanie wysokości wierszy
        row_heights = []
        for i in range(nrows):
            if i == 0:
                row_heights.append(0.6 * cm)   # nagłówek
            elif i == nrows - 1:
                row_heights.append(0.5 * cm)  # stopka
            else:
                row_heights.append(0.35 * cm)  # subwiersze

        t = Table(
            subtable_matrix,
            colWidths=col_widths,
            rowHeights=row_heights,
            repeatRows=1
        )

        style_subtable(t)
        story.append(t)

        current_start += chunk_size
        lp_start += chunk_size

        # Jeśli jeszcze zostały wiersze do przetworzenia, wstawiamy podział strony
        if current_start < num_rows:
            story.append(PageBreak())

    doc.build(story)
    open_pdf(pdf_file_name)


def open_pdf(pdf_file_name):
    """
    Otwiera PDF w systemowym domyślnym programie.
    """
    if platform.system() == 'Windows':
        os.startfile(pdf_file_name)
    elif platform.system() == 'Darwin':  # macOS
        os.system(f'open "{pdf_file_name}"')
    else:  # Linux / inne
        os.system(f'xdg-open "{pdf_file_name}"')


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Użycie: python RozliczKarty2.py <nazwa_pliku.json>")
        sys.exit(1)

    file_name = sys.argv[1]
    generate_pdf(file_name)
