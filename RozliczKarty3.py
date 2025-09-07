import json
import sys
import calendar
import os
import subprocess

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, portrait
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_LEFT, TA_CENTER


def easter_date(year):
    """
    Zwraca krotkę (month, day) z datą Wielkanocy dla danego roku (kalendarz gregoriański).
    Algorytm Gaussa.
    """
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return (month, day)


def format_easter(year):
    """Zwraca datę Wielkanocy w formacie 'dd-mm'."""
    m, d = easter_date(year)
    return f"{d:02d}-{m:02d}"


def map_work_hours(value):
    """
    Mapuje wartość z JSON na liczbę godzin pracy.
    Jeśli wartość to 1, 2 lub 3, zwraca 8.
    W przeciwnym wypadku próbuje zwrócić wartość jako liczbę całkowitą.
    """
    try:
        return 8 if int(value) in [1, 2, 3] else int(value)
    except (ValueError, TypeError):
        return value  # Zwraca oryginalną wartość, jeśli nie jest liczbą


def load_table_from_file(file_name):
    """
    Wczytuje strukturę danych z pliku JSON.
    """
    try:
        with open(file_name, "r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        raise FileNotFoundError(f"Plik {file_name} nie istnieje!")
    except json.JSONDecodeError:
        raise ValueError(f"Błąd w formacie JSON w pliku {file_name}!")


def open_pdf(path):
    """
    Otwiera plik PDF w domyślnym programie systemu operacyjnego.
    - Windows: os.startfile(...)
    - macOS: subprocess.call(["open", ...])
    - Linux: subprocess.call(["xdg-open", path])
    """
    if sys.platform.startswith('win'):
        os.startfile(path)
    elif sys.platform.startswith('darwin'):
        subprocess.call(["open", path])
    else:
        subprocess.call(["xdg-open", path])


def save_tables_to_pdf(file_name, table_data):
    """
    Generuje plik PDF na podstawie danych w table_data.
    Nazwa pliku PDF to: karta_<grupa>_<miesiąc>_<rok>.pdf
    """
    group = table_data.get("group", "NieznanaGrupa")
    month = table_data.get("month", "NieznanyMiesiac")
    year = table_data.get("year", "2025")

    # Polskie miesiące:
    polish_months = {
        "Styczeń": 1, "Luty": 2, "Marzec": 3, "Kwiecień": 4, "Maj": 5, "Czerwiec": 6,
        "Lipiec": 7, "Sierpień": 8, "Wrzesień": 9, "Październik": 10, "Listopad": 11, "Grudzień": 12
    }
    month_number = polish_months.get(month, 1)

    days_in_month = calendar.monthrange(int(year), month_number)[1]

    data = table_data.get("data", {})
    users = list(data.keys())

    if not users:
        raise ValueError("Brak użytkowników w pliku JSON!")

    # Lista standardowych świąt
    holidays = [
        "01-01",  # Nowy Rok
        "06-01",  # Trzech Króli
        "01-05",  # Święto Pracy
        "03-05",  # Konstytucja 3 Maja
        "15-08",  # Wniebowzięcie NMP
        "01-11",  # Wszystkich Świętych
        "11-11",  # Święto Niepodległości
        "25-12",  # 1. dzień Bożego Narodzenia
        "26-12",  # 2. dzień Bożego Narodzenia
    ]

    # Święta liczone zawsze jako 16 godzin:
    # (Tylko jeśli w JSON wartość to 1,2,3 i data_key w holidays_16, w kolumnie "Święta" = 16)
    year_int = int(year)
    easter_str = format_easter(year_int)
    holidays_16 = [
        "01-01",   # Nowy Rok
        "25-12",   # 1. dzień Bożego Narodzenia
        "26-12",   # 2. dzień Bożego Narodzenia
        easter_str  # Wielkanoc
    ]

    # Przygotowanie nazwy pliku PDF z przedrostkiem "karta_"
    # np. "karta_GrupaA_Styczeń_2025.pdf"
    pdf_file_name = f"karta_{group}_{month}_{year}.pdf"

    # Rejestracja czcionki DejaVu Sans (jeśli dostępna)
    try:
        pdfmetrics.registerFont(TTFont('DejaVu', 'DejaVuSans.ttf'))
    except:
        pass

    styles = getSampleStyleSheet()
    style_title = ParagraphStyle(
        'Title_DejaVu',
        parent=styles['Title'],
        fontName='DejaVu',
        fontSize=12,
        leading=14,
        alignment=TA_LEFT
    )
    style_heading2 = ParagraphStyle(
        'Heading2_DejaVu',
        parent=styles['Heading2'],
        fontName='DejaVu',
        fontSize=10,
        leading=12,
        alignment=TA_LEFT
    )
    style_normal = ParagraphStyle(
        'Normal_DejaVu',
        parent=styles['Normal'],
        fontName='DejaVu',
        fontSize=10,
        leading=12
    )
    style_heading4 = ParagraphStyle(
        'Heading4_DejaVu',
        parent=styles['Heading4'],
        fontName='DejaVu',
        fontSize=10,
        leading=12,
        alignment=TA_CENTER
    )

    scaling_factor = 5
    tk_label_width = 11
    col_width = tk_label_width * scaling_factor
    col_widths = [col_width] * 9

    # Tworzymy dokument PDF
    pdf = SimpleDocTemplate(
        pdf_file_name,
        pagesize=portrait(A4),
        leftMargin=30,
        rightMargin=30,
        topMargin=30,
        bottomMargin=30
    )
    elements = []

    for user in users:
        # Zmienne podsumowujące wartości w każdej kolumnie
        total_work_hours = 0
        total_holidays_val = 0
        total_praca_nocna = 0
        total_urlop_wypoczynkowy = 0
        total_chorobowe = 0
        total_urlop_okolicznosciowy = 0
        total_opieka_nad_dzieckiem = 0
        total_inne = 0

        user_values = data[user]

        main_header = f"MIESIĘCZNA KARTA PRACY          {
            group.replace('_users', '')}"
        sub_header_text = f"Nazwisko i Imię: {
            user}           |          Miesiąc: {month} {year}"

        # Definicja tabeli z nagłówkami
        table_data_pdf = [
            [Paragraph(main_header, style_title)],
            [Paragraph(sub_header_text, style_heading2)],
            [
                Paragraph("Data", style_heading4),
                Paragraph("Liczba\ngodzin pracy", style_heading4),
                Paragraph("Święta", style_heading4),
                Paragraph("Praca nocna", style_heading4),
                Paragraph("Urlop\nwypoczynkowy", style_heading4),
                Paragraph("Chorobowe", style_heading4),
                Paragraph("Urlop\nokolicznościowy", style_heading4),
                Paragraph("Opieka\nnad dzieckiem", style_heading4),
                Paragraph("Inne", style_heading4)
            ]
        ]

        for day in range(1, days_in_month + 1):
            weekday = calendar.weekday(int(year), month_number, day)
            date_key = f"{day:02d}-{month_number:02d}"

            # Pobieramy wpis z JSON (jeśli istnieje) i konwertujemy do int (jeśli można)
            raw_value = user_values[day - 1] if day - \
                1 < len(user_values) else ""
            try:
                int_value = int(raw_value)
            except (ValueError, TypeError):
                int_value = None

            # Mapowanie wartości według wpisanego skrótu/oznaczenia
            if isinstance(raw_value, str) and raw_value.lower() == "w":
                work_hours = "w"
                urlop_wypoczynkowy = "8"
                chorobowe = ""
                urlop_okolicznosciowy = ""
                opieka_nad_dzieckiem = ""
                inne = ""
            elif isinstance(raw_value, str) and raw_value.lower() == "c":
                work_hours = "c"
                urlop_wypoczynkowy = ""
                chorobowe = "8"
                urlop_okolicznosciowy = ""
                opieka_nad_dzieckiem = ""
                inne = ""
            elif isinstance(raw_value, str) and raw_value.lower() == "xz":
                work_hours = "8z"
                urlop_wypoczynkowy = ""
                chorobowe = ""
                urlop_okolicznosciowy = ""
                opieka_nad_dzieckiem = ""
                inne = ""
            elif isinstance(raw_value, str) and raw_value.lower() == "up":
                work_hours = "up"
                urlop_wypoczynkowy = ""
                chorobowe = ""
                urlop_okolicznosciowy = ""
                opieka_nad_dzieckiem = ""
                inne = "8"
            elif isinstance(raw_value, str) and raw_value.lower() == "uo":
                work_hours = "uo"
                urlop_wypoczynkowy = ""
                chorobowe = ""
                urlop_okolicznosciowy = "8"
                opieka_nad_dzieckiem = ""
                inne = ""
            elif isinstance(raw_value, str) and raw_value.lower() == "upk":
                work_hours = "upk"
                urlop_wypoczynkowy = ""
                chorobowe = ""
                urlop_okolicznosciowy = ""
                opieka_nad_dzieckiem = "8"
                inne = ""
            elif isinstance(raw_value, str) and raw_value.lower() == "de":
                work_hours = "de"
                urlop_wypoczynkowy = ""
                chorobowe = ""
                urlop_okolicznosciowy = ""
                opieka_nad_dzieckiem = ""
                inne = "8"
            elif isinstance(raw_value, str) and raw_value.lower() == "nu":
                work_hours = "nu"
                urlop_wypoczynkowy = ""
                chorobowe = ""
                urlop_okolicznosciowy = ""
                opieka_nad_dzieckiem = ""
                inne = ""
            elif isinstance(raw_value, str) and raw_value.lower() == "mo":
                work_hours = "mo"
                urlop_wypoczynkowy = ""
                chorobowe = ""
                urlop_okolicznosciowy = ""
                opieka_nad_dzieckiem = ""
                inne = "8"
            elif isinstance(raw_value, str) and raw_value.lower() == "ub":
                work_hours = "ub"
                urlop_wypoczynkowy = ""
                chorobowe = ""
                urlop_okolicznosciowy = ""
                opieka_nad_dzieckiem = ""
                inne = ""
            elif isinstance(raw_value, str) and raw_value.lower() == "wż":
                work_hours = "wż"
                urlop_wypoczynkowy = "8"
                chorobowe = ""
                urlop_okolicznosciowy = ""
                opieka_nad_dzieckiem = ""
                inne = ""
            elif isinstance(raw_value, str) and raw_value.lower() == "sz":
                work_hours = "sz"
                urlop_wypoczynkowy = ""
                chorobowe = ""
                urlop_okolicznosciowy = ""
                opieka_nad_dzieckiem = ""
                inne = "8"
            elif isinstance(raw_value, str) and raw_value.lower() == "ws":
                work_hours = "ws"
                urlop_wypoczynkowy = ""
                chorobowe = ""
                urlop_okolicznosciowy = ""
                opieka_nad_dzieckiem = ""
                inne = "8"
            else:
                # Jeśli nie rozpoznano skrótu, spróbujmy z map_work_hours
                work_hours = map_work_hours(raw_value)
                urlop_wypoczynkowy = ""
                chorobowe = ""
                urlop_okolicznosciowy = ""
                opieka_nad_dzieckiem = ""
                inne = ""

            # Sprawdzamy dzień tygodnia i święta
            is_sunday = (weekday == 6)
            is_holiday = (date_key in holidays)
            is_16holiday = (date_key in holidays_16)

            # Logika kolumny „Święta”
            if is_sunday:
                if int_value in [1, 2, 3]:
                    holiday_text = "8"
                else:
                    holiday_text = ""
            elif is_holiday:
                if is_16holiday and int_value in [1, 2, 3]:
                    holiday_text = "16"
                else:
                    if int_value in [1, 2, 3]:
                        holiday_text = "8"
                    # Jeśli wartość wpisu jest niepustym ciągiem, ale nie jest 'xz', ustawiamy "X"
                    elif raw_value.strip() != "" and raw_value.lower() != "xz":
                        holiday_text = "X"
                    else:
                        holiday_text = ""
            else:
                holiday_text = ""

            # Praca nocna – kolumna "Praca nocna" (wartość "8" jeśli int_value == 3)
            praca_nocna = "8" if int_value == 3 else ""

            # SUMOWANIE do kolumn zbiorczych
            if isinstance(work_hours, int):
                total_work_hours += work_hours
            elif isinstance(work_hours, str) and work_hours.endswith("z"):
                # np. "8z" -> 8
                try:
                    godz = int(work_hours.replace("z", ""))
                    total_work_hours += godz
                except:
                    pass

            if holiday_text.isdigit():
                total_holidays_val += int(holiday_text)

            if praca_nocna.isdigit():
                total_praca_nocna += int(praca_nocna)

            if urlop_wypoczynkowy.isdigit():
                total_urlop_wypoczynkowy += int(urlop_wypoczynkowy)

            if chorobowe.isdigit():
                total_chorobowe += int(chorobowe)

            if urlop_okolicznosciowy.isdigit():
                total_urlop_okolicznosciowy += int(urlop_okolicznosciowy)

            if opieka_nad_dzieckiem.isdigit():
                total_opieka_nad_dzieckiem += int(opieka_nad_dzieckiem)

            if inne.isdigit():
                total_inne += int(inne)

            # Dodajemy wiersz do PDF
            table_data_pdf.append([
                Paragraph(str(day), style_normal),
                Paragraph(str(work_hours) if work_hours else "", style_normal),
                Paragraph(holiday_text, style_normal),
                Paragraph(praca_nocna, style_normal),
                Paragraph(urlop_wypoczynkowy, style_normal),
                Paragraph(chorobowe, style_normal),
                Paragraph(urlop_okolicznosciowy, style_normal),
                Paragraph(opieka_nad_dzieckiem, style_normal),
                Paragraph(inne, style_normal)
            ])

        # Wiersz podsumowania
        summary_row = [
            Paragraph("Razem", style_normal),
            Paragraph(str(total_work_hours), style_normal),
            Paragraph(str(total_holidays_val)
                      if total_holidays_val else "", style_normal),
            Paragraph(str(total_praca_nocna)
                      if total_praca_nocna else "", style_normal),
            Paragraph(str(total_urlop_wypoczynkowy)
                      if total_urlop_wypoczynkowy else "", style_normal),
            Paragraph(str(total_chorobowe)
                      if total_chorobowe else "", style_normal),
            Paragraph(str(total_urlop_okolicznosciowy)
                      if total_urlop_okolicznosciowy else "", style_normal),
            Paragraph(str(total_opieka_nad_dzieckiem)
                      if total_opieka_nad_dzieckiem else "", style_normal),
            Paragraph(str(total_inne) if total_inne else "", style_normal)
        ]
        table_data_pdf.append(summary_row)

        # Wiersz z podpisem
        signature_text = "Podpis wystawiającego: ____________________"
        signature_row = [Paragraph(signature_text, style_normal)] + [""] * 8
        table_data_pdf.append(signature_row)

        # Budowanie Tabeli
        t = Table(table_data_pdf, colWidths=col_widths, hAlign='LEFT')
        style = TableStyle([
            # Nagłówek główny (pierwszy wiersz)
            ('SPAN', (0, 0), (-1, 0)),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('BOX', (0, 0), (-1, 0), 1, colors.black),
            ('ALIGN', (0, 0), (-1, 0), 'LEFT'),

            # Subheader (drugi wiersz)
            ('SPAN', (0, 1), (-1, 1)),
            ('BACKGROUND', (0, 1), (-1, 1), colors.lightgrey),
            ('BOX', (0, 1), (-1, 1), 1, colors.black),
            ('ALIGN', (0, 1), (-1, 1), 'LEFT'),

            # Nagłówki kolumn (trzeci wiersz)
            ('BACKGROUND', (0, 2), (-1, 2), colors.lightgrey),
            ('TEXTCOLOR', (0, 2), (-1, 2), colors.black),
            ('FONTNAME', (0, 2), (-1, 2), 'DejaVu'),
            ('FONTSIZE', (0, 2), (-1, 2), 10),
            ('ALIGN', (0, 2), (-1, 2), 'CENTER'),
            ('GRID', (0, 2), (-1, -1), 1, colors.black),

            # Czcionka
            ('FONTNAME', (0, 0), (-1, -1), 'DejaVu'),
        ])

        # Pokolorowanie kolumny "Data"
        for i, row_data in enumerate(table_data_pdf[3:-2], start=3):
            day_val = row_data[0].text
            if day_val.isdigit():
                day_int = int(day_val)
                d_key = f"{day_int:02d}-{month_number:02d}"
                wd = calendar.weekday(int(year), month_number, day_int)
                holiday_check = (d_key in holidays)
                if wd == 6 or holiday_check:
                    bg_color = colors.red
                elif wd == 5:  # Sobota
                    bg_color = colors.green
                else:
                    bg_color = colors.white
                style.add('BACKGROUND', (0, i), (0, i), bg_color)

        # Wiersz "Razem" (przedostatni wiersz)
        summary_index = len(table_data_pdf) - 2
        style.add('BACKGROUND', (0, summary_index),
                  (-1, summary_index), colors.lightgrey)
        style.add('ALIGN', (0, summary_index), (-1, summary_index), 'CENTER')

        # Wiersz "Podpis" (ostatni wiersz)
        signature_index = len(table_data_pdf) - 1
        style.add('SPAN', (0, signature_index), (-1, signature_index))
        style.add('BOX', (0, signature_index),
                  (-1, signature_index), 1, colors.black)
        style.add('ALIGN', (0, signature_index), (-1, signature_index), 'LEFT')
        style.add('LEFTPADDING', (0, signature_index),
                  (-1, signature_index), 5)
        style.add('BOTTOMPADDING', (0, signature_index),
                  (-1, signature_index), 10)

        t.setStyle(style)
        elements.append(t)
        elements.append(Spacer(1, 12))
        elements.append(PageBreak())

    # Zapis do pliku PDF
    pdf.build(elements)
    print(f"Plik PDF '{pdf_file_name}' został utworzony.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Użycie: python RozliczKarty3.py <nazwa_pliku.json>")
        sys.exit(1)

    # Odczytujemy nazwę pliku JSON z argumentów
    file_name = sys.argv[1]

    # 1. Wczytanie danych z pliku JSON
    table_data = load_table_from_file(file_name)

    # 2. Zapis do PDF (z nazwą grupy, miesiąca i roku z przedrostkiem "karta_")
    save_tables_to_pdf(file_name, table_data)

    # 3. Otworzenie PDF w domyślnym programie
    group = table_data.get("group", "NieznanaGrupa")
    month = table_data.get("month", "NieznanyMiesiac")
    year = table_data.get("year", "2025")
    pdf_file_name = f"karta_{group}_{month}_{year}.pdf"

    open_pdf(pdf_file_name)
