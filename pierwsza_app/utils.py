import json, calendar
from pathlib import Path
from django.conf import settings

BASE_DIR = Path(settings.BASE_DIR)

POLISH_MONTHS = { "Styczeń":1, "Luty":2, "Marzec":3, "Kwiecień":4, "Maj":5, "Czerwiec":6,
                  "Lipiec":7, "Sierpień":8, "Wrzesień":9, "Październik":10, "Listopad":11, "Grudzień":12 }

# ---- GRUPY (działy) ----
GROUPS_FILE = BASE_DIR / "groups.json"

def load_groups():
    if GROUPS_FILE.exists():
        try:
            return json.loads(GROUPS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []

def save_groups(groups):
    data = []
    for g in groups:
        # przechowujemy tylko dane, bez „widżetów” (jak w Tkinter) :contentReference[oaicite:2]{index=2}
        data.append({"name": g["name"].strip(), "login": g["login"], "password": g["password"]})
    GROUPS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def get_group(groups, name):
    name = name.strip()
    for g in groups:
        if g["name"].strip() == name:
            return g
    return None

# ---- UŻYTKOWNICY (pracownicy) ----
def users_path(group: str) -> Path:
    return BASE_DIR / f"{group}_users.json"

def load_users_from_file(group: str):
    p = users_path(group)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []

def save_users_to_file(group: str, users: list[str]):
    p = users_path(group)
    p.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")

# ---- DANE MIESIĄCA (grafik) ----
def month_json_path(group: str, month: str, year: str|int) -> Path:
    return BASE_DIR / f"{group}_{month}_{year}.json"

def load_month_data(group, month, year):
    p = month_json_path(group, month, year)
    if p.exists():
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
            return obj.get("data", {})
        except Exception:
            return {}
    return {}

def save_table_to_file(group, month, year, table_dict):
    p = month_json_path(group, month, year)
    payload = {"group": group, "month": month, "year": str(year), "data": table_dict}
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=4), encoding="utf-8")
    return str(p)

def days_in_month(month, year):
    return calendar.monthrange(int(year), POLISH_MONTHS[month])[1]
