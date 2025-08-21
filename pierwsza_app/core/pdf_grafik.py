# wrapper na Twoje RozliczKarty2
# używamy Twojej funkcji 1:1  :contentReference[oaicite:6]{index=6}
from RozliczKarty2 import generate_pdf as _gen


# pierw…/core/pdf_grafik.py
def generate_pdf_from_json(json_path):
    # import dopiero w chwili użycia
    from RozliczKarty2 import generate_pdf as _gen
    return _gen(json_path)
