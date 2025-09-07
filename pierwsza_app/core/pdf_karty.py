# C:\Users\PC\moja_aplikacja\pierwsza_app\core\pdf_karty.py
# Wrapper do generowania PDF „karty” z Twojego RozliczKarty3.py
# Import jest leniwy (wewnątrz funkcji), żeby serwer startował bez czcionek.

from pathlib import Path
import json
import os


def generate_karty_pdf_from_json(json_path: str):
    """
    Generuje PDF „karty” na podstawie pliku JSON zapisanym przez widok.
    Zwraca ścieżkę do wygenerowanego pliku PDF (albo None, jeśli nie znaleziono).
    """
    # >>>> LENIWY IMPORT – dopiero przy wywołaniu <<<<
    from RozliczKarty3 import save_tables_to_pdf as _save

    # Wczytaj dane z JSON – Twój oryginalny kod oczekuje (file_name, table_data)
    with open(json_path, "r", encoding="utf-8") as f:
        table_data = json.load(f)

    # Uruchom Twoją funkcję generującą PDF
    # (Twój RozliczKarty3 zwykle tworzy plik o nazwie: karta_{group}_{month}_{year}.pdf)
    _save(json_path, table_data)

    # Spróbuj wywnioskować nazwę PDF na podstawie danych
    group = table_data.get("group")
    month = table_data.get("month")
    year = table_data.get("year")

    # Domyślna oczekiwana nazwa według Twojej konwencji:
    if group and month and year:
        pdf_name = f"karta_{group}_{month}_{year}.pdf"
        if os.path.exists(pdf_name):
            return pdf_name

    # Gdyby nazwa była inna – spróbuj znaleźć pierwszy plik „karta_*.pdf” obok JSON
    candidates = sorted(Path(json_path).parent.glob("karta_*.pdf"))
    return str(candidates[0]) if candidates else None