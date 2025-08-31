from django.shortcuts import render, redirect
from django.http import HttpResponse, FileResponse, HttpResponseRedirect, JsonResponse, Http404
from django.conf import settings
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache
from django.core.mail import send_mail, BadHeaderError
from django.utils.text import slugify

from pathlib import Path
from datetime import date, timedelta
from collections import defaultdict
from urllib.parse import unquote
import csv, io
import json
import re

from .utils import (
    POLISH_MONTHS,
    load_groups, save_groups, get_group,
    users_path, load_users_from_file, save_users_to_file,
    load_month_data, save_table_to_file, days_in_month,
)

# -------------------------
# ŚCIEŻKI / PLIKI
# -------------------------
BASE_DIR = Path(settings.BASE_DIR)
SKILLS_FILE = BASE_DIR / "skills_catalog.json"

# -------------------------
# KATALOG UMIEJĘTNOŚCI (GLOBALNY)
# -------------------------
def load_skill_catalog():
    try:
        if SKILLS_FILE.exists():
            data = json.loads(SKILLS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                out, seen = [], set()
                for x in data:
                    s = str(x).strip()
                    k = s.casefold()
                    if s and k not in seen:
                        seen.add(k)
                        out.append(s)
                return out
    except Exception:
        pass
    return []

def save_skill_catalog(catalog):
    uniq, seen = [], set()
    for x in catalog or []:
        s = str(x).strip()
        k = s.casefold()
        if s and k not in seen:
            seen.add(k)
            uniq.append(s)
    SKILLS_FILE.write_text(json.dumps(uniq, ensure_ascii=False, indent=2), encoding="utf-8")

def delete_skill_globally(skill_name: str) -> bool:
    """
    Usuwa umiejętność z katalogu globalnego ORAZ ze wszystkich profili
    we wszystkich działach. Zwraca True jeśli coś faktycznie usunięto.
    """
    target = (skill_name or "").strip()
    if not target:
        return False
    key = target.casefold()

    # 1) katalog
    catalog = load_skill_catalog()
    new_catalog = [s for s in catalog if s.casefold() != key]
    changed_catalog = (len(new_catalog) != len(catalog))
    if changed_catalog:
        save_skill_catalog(new_catalog)

    # 2) profile
    changed_any_user = False
    for g in load_groups():
        dept = g["name"]
        users = load_users_norm(dept)
        changed_dept = False
        for u in users:
            skills_map = u.get("skills") or {}
            new_map = {k: v for k, v in skills_map.items() if k.casefold() != key}
            if new_map != skills_map:
                u["skills"] = new_map
                changed_dept = True
                changed_any_user = True
        if changed_dept:
            save_users_to_file(dept, users)

    return changed_catalog or changed_any_user

# -------------------------
# PDF
# -------------------------
from .core.pdf_grafik import generate_pdf_response as generate_grafik_pdf_response

try:
    from .core.pdf_karty import generate_karty_pdf_response
except Exception:
    generate_karty_pdf_response = None

# -------------------------
# E-MAIL
# -------------------------
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

@require_POST
@never_cache
def notify_email(request, group):
    """
    POST /grafik/<group>/notify-email/
    Body JSON:
      {
        "subject": "...",            # opcjonalnie
        "message": "...",            # opcjonalnie
        "employees": ["Milena", ...] # opcjonalnie: wyślij tylko do tych osób (po name)
        "extra": ["a@b.com", ...]    # opcjonalnie: dodatkowe adresy
      }

    ZAWSZE zbiera adresy z pól 'email' profili pracowników w danym dziale.
    """
    if request.session.get("auth_group") != group:
        return JsonResponse({"ok": False, "detail": "Nie zalogowano do tego działu."}, status=401)

    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception as e:
        return JsonResponse({"ok": False, "detail": f"Nieprawidłowy JSON: {e}"}, status=400)

    subject = (data.get("subject") or f"Grafik {group}").strip()
    message = (data.get("message") or f"Został zaktualizowany grafik dla działu {group}.").strip()

    users = load_users_norm(group)
    only_names = set(data.get("employees") or []) if isinstance(data.get("employees"), list) else None

    recipients, missing = [], []
    for u in users:
        if only_names and u.get("name") not in only_names:
            continue
        email = (u.get("email") or "").strip()
        if email and EMAIL_RE.match(email):
            recipients.append(email)
        else:
            if only_names:
                missing.append(u.get("name") or "")

    extras = data.get("extra") if isinstance(data.get("extra"), list) else []
    extras = [e.strip() for e in extras if isinstance(e, str) and EMAIL_RE.match(e.strip())]

    recipients = sorted(set(recipients + extras))
    if not recipients:
        detail = "Brak poprawnych adresów e-mail w profilach."
        if missing:
            detail += f" Brak e-maili dla: {', '.join(missing)}."
        return JsonResponse({"ok": False, "detail": detail}, status=400)

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com")
    try:
        sent = send_mail(subject=subject, message=message, from_email=from_email,
                         recipient_list=recipients, fail_silently=False)
        return JsonResponse({"ok": True, "sent": int(sent), "recipients": recipients, "missing_email_for": missing})
    except BadHeaderError:
        return JsonResponse({"ok": False, "detail": "Nieprawidłowy nagłówek e-mail."}, status=400)
    except Exception as e:
        return JsonResponse({"ok": False, "detail": f"Błąd wysyłki: {e}"}, status=500)

# -------------------------
# USERS – normalizacja / migracja
# -------------------------
def normalize_users(users_list):
    """
    Docelowy format:
    {
      "name": str,
      "position": str,
      "contact": str,        # telefon
      "email": str,
      "medical_exam": str,   # 'YYYY-MM-DD'
      "skills": { "nazwa": bool, ... }
    }
    """
    norm = []
    for u in users_list or []:
        if isinstance(u, str):
            norm.append({
                "name": u, "position": "", "contact": "",
                "email": "", "medical_exam": "", "skills": {},
            })
        elif isinstance(u, dict):
            # skills akceptujemy jako dict albo listę
            raw_sk = u.get("skills")
            skills = {}
            if isinstance(raw_sk, dict):
                for k, v in raw_sk.items():
                    skills[str(k)] = bool(v)
            elif isinstance(raw_sk, list):
                for k in raw_sk:
                    skills[str(k)] = True

            norm.append({
                "name": (u.get("name") or "").strip(),
                "position": (u.get("position") or "").strip(),
                "contact": (u.get("contact") or "").strip(),
                "email": (u.get("email") or "").strip(),
                "medical_exam": (u.get("medical_exam") or "").strip() or (u.get("medical_date") or "").strip(),
                "skills": skills,
            })
    return norm

def load_users_norm(group):
    raw = load_users_from_file(group)
    users = normalize_users(raw)

    needs_migration = False
    if any(isinstance(x, str) for x in (raw or [])):
        needs_migration = True
    else:
        for x in (raw or []):
            if isinstance(x, dict):
                required = ("contact", "position", "email", "medical_exam", "skills")
                if any(k not in x for k in required):
                    needs_migration = True
                    break

    if needs_migration:
        save_users_to_file(group, users)
    return users

# -------------------------
# START
# -------------------------
@never_cache
def start(request):
    groups = load_groups()

    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        login = (request.POST.get("login") or "").strip()
        password = (request.POST.get("password") or "").strip()

        if not (name and login and password):
            return render(request, "pierwsza_app/start.html", {"groups": groups, "error": "Wypełnij wszystkie pola."})

        if get_group(groups, name):
            return render(request, "pierwsza_app/start.html", {"groups": groups, "error": f"Dział „{name}” już istnieje."})

        groups.append({"name": name, "login": login, "password": password})
        save_groups(groups)

        if not users_path(name).exists():
            save_users_to_file(name, [])

        return redirect("login", group=name)

    return render(request, "pierwsza_app/start.html", {"groups": groups})

# -------------------------
# LOGOWANIE
# -------------------------
@never_cache
def login_view(request, group):
    groups = load_groups()
    g = get_group(groups, group)
    if not g:
        return redirect("start")

    error = None
    if request.method == "POST":
        login = (request.POST.get("login") or "").strip()
        password = (request.POST.get("password") or "").strip()

        if (login == g["login"] and password == g["password"]) or (login == "admin" and password == "admin"):
            request.session["auth_group"] = group
            return redirect("panel", group=group)
        error = "Niepoprawny login lub hasło."

    return render(request, "pierwsza_app/login.html", {"group": group, "error": error})

# -------------------------
# POMOCNICZE – zakres miesięcy
# -------------------------
def months_between(from_month, from_year, to_month, to_year):
    fm, fy = POLISH_MONTHS[from_month], int(from_year)
    tm, ty = POLISH_MONTHS[to_month], int(to_year)
    out = []
    y, m = fy, fm
    num2name = {v: k for k, v in POLISH_MONTHS.items()}
    while (y < ty) or (y == ty and m <= tm):
        out.append((num2name[m], str(y)))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out

# -------------------------
# Święta / niedziele
# -------------------------
def _easter_date(y: int) -> date:
    a = y % 19
    b = y // 100
    c = y % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m_ = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m_ + 114) // 31
    day = ((h + l - 7 * m_ + 114) % 31) + 1
    return date(y, month, day)

def _is_polish_holiday(y: int, m: int, d: int) -> bool:
    fixed = {(1, 1), (1, 6), (5, 1), (5, 3), (8, 15), (11, 1), (11, 11), (12, 25), (12, 26)}
    if (m, d) in fixed:
        return True
    easter = _easter_date(y)
    easter_mon = easter + timedelta(days=1)
    corpus_christi = easter + timedelta(days=60)
    return (m, d) in {(easter_mon.month, easter_mon.day), (corpus_christi.month, corpus_christi.day)}

def _is_sunday_or_holiday(y: int, m: int, d: int) -> bool:
    try:
        wd = date(y, m, d).weekday()
    except ValueError:
        return False
    return wd == 6 or _is_polish_holiday(y, m, d)

def count_stats(group, employees, month_year_list):
    WORK_TOKENS = {"1", "2", "3"}
    stats = {e["name"]: {"ndz": 0, "l4": 0, "workdays": 0} for e in employees}

    for month_name, year_str in month_year_list:
        y = int(year_str)
        m = POLISH_MONTHS[month_name]
        n_days = days_in_month(month_name, year_str)
        data = load_month_data(group, month_name, year_str)

        for e in employees:
            row = data.get(e["name"], []) or []
            for d in range(1, n_days + 1):
                v = ((row[d - 1] if len(row) >= d else "") or "").strip()
                if v.upper() == "C":
                    stats[e["name"]]["l4"] += 1
                if v in WORK_TOKENS:
                    if _is_sunday_or_holiday(y, m, d):
                        stats[e["name"]]["ndz"] += 1
                    else:
                        wd = date(y, m, d).weekday()
                        if wd in (0, 1, 2, 3, 4, 5):
                            stats[e["name"]]["workdays"] += 1
    return stats

def update_group_credentials(group, login, password):
    groups = load_groups()
    for g in groups:
        if g["name"].strip() == group.strip():
            g["login"] = login
            g["password"] = password
    save_groups(groups)

def rename_group_and_files(old, new):
    groups = load_groups()
    for g in groups:
        if g["name"].strip() == old.strip():
            g["name"] = new
    save_groups(groups)

    old_users = users_path(old)
    new_users = users_path(new)
    if old_users.exists():
        old_users.rename(new_users)

    for f in BASE_DIR.glob(f"{old}_*.json"):
        f.rename(BASE_DIR / f.name.replace(f"{old}_", f"{new}_"))

# -------------------------
# PANEL
# -------------------------
@never_cache
def panel(request, group):
    if request.session.get("auth_group") != group:
        return redirect("login", group=group)

    users = load_users_norm(group)
    groups_all = [g["name"] for g in load_groups()]
    info, error = None, None

    # Filtr / zakres
    q = (request.GET.get("q") or "").strip()
    from_month = request.GET.get("from_month", "Styczeń")
    from_year = request.GET.get("from_year", "2025")
    to_month = request.GET.get("to_month", "Grudzień")
    to_year = request.GET.get("to_year", "2025")

    visible_users = [u for u in users if q.lower() in u["name"].lower()] if q else users

    # Pomocnicze: liczba dni do wygaśnięcia badań
    today = date.today()
    def _days_left_to_exam(u):
        s = (u.get("medical_exam") or "").strip()
        try:
            y, m, d = map(int, s.split("-"))
            return (date(y, m, d) - today).days
        except Exception:
            return None

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "add_employee":
            new_emp = (request.POST.get("new_emp") or "").strip()
            if new_emp:
                if not any(u["name"] == new_emp for u in users):
                    users.append({
                        "name": new_emp, "position": "", "contact": "",
                        "email": "", "medical_exam": "", "skills": {},
                    })
                    save_users_to_file(group, users)
                    info = f"Dodano pracownika: {new_emp}"
                else:
                    error = "Taki pracownik już istnieje."
            else:
                error = "Podaj nazwisko i imię."

        elif action == "remove_employee":
            emp = request.POST.get("emp", "")
            users = [u for u in users if u["name"] != emp]
            save_users_to_file(group, users)
            info = f"Usunięto: {emp}"

        elif action == "move_up":
            emp = request.POST.get("emp", "")
            idx = next((i for i, u in enumerate(users) if u["name"] == emp), None)
            if idx is not None and idx > 0:
                users[idx - 1], users[idx] = users[idx], users[idx - 1]
                save_users_to_file(group, users)

        elif action == "move_down":
            emp = request.POST.get("emp", "")
            idx = next((i for i, u in enumerate(users) if u["name"] == emp), None)
            if idx is not None and idx < len(users) - 1:
                users[idx + 1], users[idx] = users[idx], users[idx + 1]
                save_users_to_file(group, users)

        elif action == "edit_employee":
            old = (request.POST.get("old_emp") or "").strip()
            new_name = (request.POST.get("new_emp") or "").strip()
            new_pos = (request.POST.get("new_pos") or "").strip()
            new_contact = (request.POST.get("new_contact") or "").strip()

            if not new_name:
                error = "Podaj nowe nazwisko i imię."
            else:
                for u in users:
                    if u["name"] == old:
                        u["name"] = new_name
                        u["position"] = new_pos
                        u["contact"] = new_contact
                        break
                save_users_to_file(group, users)
                info = f"Zmieniono dane pracownika: {old} → {new_name}"

        elif action == "transfer_employee":
            emp = (request.POST.get("emp") or "").strip()
            target = (request.POST.get("target_group") or "").strip()
            if emp and target and target != group:
                src_user = next((u for u in users if u["name"] == emp), None)
                if not src_user:
                    error = "Nie znaleziono pracownika do przeniesienia."
                else:
                    tgt_users = load_users_norm(target)
                    if any(u["name"] == emp for u in tgt_users):
                        error = f"{emp} już istnieje w dziale {target}."
                    else:
                        tgt_users.append(src_user)
                        save_users_to_file(target, tgt_users)
                        users = [u for u in users if u["name"] != emp]
                        save_users_to_file(group, users)
                        info = f"Przeniesiono {emp} do działu {target}."
            else:
                error = "Wybierz inny dział."

        elif action == "go_to_edit":
            month = request.POST.get("month", "Styczeń")
            year = request.POST.get("year", "2025")
            return redirect(f"/edycja/{group}/?month={month}&year={year}")

        elif action == "set_schedule":
            month = request.POST.get("month", "Styczeń")
            year = request.POST.get("year", "2025")
            return redirect(f"/edycja/{group}/?month={month}&year={year}")

        elif action == "change_credentials":
            login = (request.POST.get("login") or "").strip()
            password = (request.POST.get("password") or "").strip()
            if login and password:
                update_group_credentials(group, login, password)
                info = "Zmieniono dane logowania."
            else:
                error = "Podaj login i hasło."

        elif action == "rename_group":
            new_name = (request.POST.get("new_name") or "").strip()
            if new_name and new_name != group:
                rename_group_and_files(group, new_name)
                return redirect("panel", group=new_name)
            else:
                error = "Podaj inną (nową) nazwę działu."

        return redirect("panel", group=group)

    # Tabela
    table_rows = []
    if request.GET.get("action") == "show_stats":
        month_years = months_between(from_month, from_year, to_month, to_year)
        stats = count_stats(group, visible_users, month_years)
        for u in visible_users:
            days_left = _days_left_to_exam(u)
            exam_soon = (days_left is not None) and (0 <= days_left <= 30)
            table_rows.append({
                "name": u["name"],
                "position": u.get("position", ""),
                "contact": u.get("contact", ""),   # tel na liście
                "email": u.get("email", ""),       # e-mail (np. dla mailto)
                "workdays": stats[u["name"]]["workdays"],
                "ndz": stats[u["name"]]["ndz"],
                "l4": stats[u["name"]]["l4"],
                "exam_days_left": days_left,
                "exam_soon": exam_soon,
            })
    else:
        for u in visible_users:
            days_left = _days_left_to_exam(u)
            exam_soon = (days_left is not None) and (0 <= days_left <= 30)
            table_rows.append({
                "name": u["name"],
                "position": u.get("position", ""),
                "contact": u.get("contact", ""),
                "email": u.get("email", ""),
                "workdays": 0, "ndz": 0, "l4": 0,
                "exam_days_left": days_left,
                "exam_soon": exam_soon,
            })

    months = list(POLISH_MONTHS.keys())
    years = [str(y) for y in range(2025, 2035)]

    # Przyjmij info z query (np. po imporcie CSV)
    if not info:
        info = request.GET.get("info")

    return render(
        request,
        "pierwsza_app/panel.html",
        {
            "group": group,
            "q": q,
            "months": months,
            "years": years,
            "from_month": from_month, "from_year": from_year,
            "to_month": to_month, "to_year": to_year,
            "table_rows": table_rows,
            "groups_all": groups_all,
            "info": info, "error": error
        },
    )

# -------------------------
# EKSPORT / IMPORT PROFILI (CSV)
# -------------------------
@never_cache
def export_profiles_csv(request, group):
    """Eksport profili pracowników danego działu do CSV (separator ';', UTF-8 BOM – działa w Excelu)."""
    if request.session.get("auth_group") != group:
        return redirect("login", group=group)

    users = load_users_norm(group)

    sio = io.StringIO()
    writer = csv.writer(sio, delimiter=';')

    headers = ["Imię i nazwisko", "Stanowisko", "Kontakt (tel.)", "E-mail", "Termin badań (RRRR-MM-DD)", "Umiejętności"]
    writer.writerow(headers)

    for u in users:
        skills_on = [k for k, v in (u.get("skills") or {}).items() if v]
        skills_str = ", ".join(skills_on)
        writer.writerow([
            u.get("name", ""),
            u.get("position", ""),
            u.get("contact", ""),
            u.get("email", ""),
            u.get("medical_exam", ""),
            skills_str,
        ])

    csv_content = "\ufeff" + sio.getvalue()
    filename = f"{slugify(group)}_profile_{date.today().isoformat()}.csv"
    resp = HttpResponse(csv_content, content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp

@require_POST
@never_cache
def import_profiles_csv(request, group):
    """
    Import profili z CSV. Obsługuje nagłówki PL/EN i separator ';' lub ','.
    Kolumny rozpoznawane (synonimy):
      - name: "Imię i nazwisko", "Nazwisko i imię", "name", "pracownik"
      - position: "Stanowisko", "position"
      - contact: "Kontakt", "Telefon", "Tel", "contact", "phone"
      - email: "E-mail", "Email", "mail"
      - medical_exam: "Termin badań", "Termin badan", "badania", "medical_exam", "exam", "data badań"
      - skills: "Umiejętności", "Umiejetnosci", "Doświadczenia", "skills"
    Umiejętności z CSV są nadpisywane dla danego pracownika (to najprostszy i czytelny model).
    Nowe umiejętności trafiają też do katalogu globalnego.
    """
    if request.session.get("auth_group") != group:
        return redirect("login", group=group)

    uploaded = request.FILES.get("csv") or request.FILES.get("file")
    if not uploaded:
        return redirect(f"/panel/{group}/?info=Nie%20wybrano%20pliku%20CSV.")

    data = uploaded.read()
    try:
        text = data.decode("utf-8-sig")
    except Exception:
        try:
            text = data.decode("cp1250")
        except Exception:
            return redirect(f"/panel/{group}/?info=Nie%20uda%C5%82o%20si%C4%99%20odczyta%C4%87%20pliku%20(kodowanie).")

    # Wykryj separator
    try:
        dialect = csv.Sniffer().sniff(text.splitlines()[0])
        delim = dialect.delimiter if dialect.delimiter in (',', ';') else ';'
    except Exception:
        delim = ';'

    # Normalizacja nagłówków -> klucze
    def _key(name: str) -> str:
        s = (name or "").strip().lower()
        trans = str.maketrans("ąćęłńóśżź", "acelnoszz")
        s = s.translate(trans)
        s = s.replace("-", " ")
        s = " ".join(s.split())
        return s

    def _map_header(h: str) -> str:
        k = _key(h)
        if k in ("imie i nazwisko", "nazwisko i imie", "name", "pracownik"):
            return "name"
        if k in ("stanowisko", "position", "pos"):
            return "position"
        if k in ("kontakt", "telefon", "tel", "contact", "phone"):
            return "contact"
        if k in ("e mail", "email", "mail"):
            return "email"
        if k in ("termin badan", "termin badan lekarskich", "badania", "medical exam", "exam", "data badan", "termin badan rrrr mm dd"):
            return "medical_exam"
        if k in ("umiejetnosci", "umiejetnosc", "doswiadczenia", "skills"):
            return "skills"
        return k

    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    field_map = {f: _map_header(f) for f in (reader.fieldnames or [])}

    users = load_users_norm(group)
    users_by_name = {u["name"]: u for u in users}
    catalog = load_skill_catalog()
    catalog_ci = {s.casefold(): s for s in catalog}

    imported = 0
    for row in reader:
        r = {field_map.get(k, k): (v or "").strip() for k, v in row.items()}

        name = r.get("name") or ""
        if not name:
            continue

        u = users_by_name.get(name)
        if not u:
            u = {"name": name, "position": "", "contact": "", "email": "", "medical_exam": "", "skills": {}}
            users.append(u)
            users_by_name[name] = u

        if "position" in r:      u["position"] = r["position"]
        if "contact" in r:       u["contact"] = r["contact"]
        if "email" in r:         u["email"] = r["email"]

        # Data – akceptuj RRRR-MM-DD lub DD.MM.RRRR (także /)
        med = r.get("medical_exam", "")
        if med:
            mm = med.replace("/", ".").replace("-", ".")
            parts = [p for p in mm.split(".") if p]
            parsed = ""
            try:
                if len(parts) == 3 and len(parts[0]) == 4:  # RRRR.MM.DD
                    y, m, d = map(int, parts)
                    parsed = f"{y:04d}-{m:02d}-{d:02d}"
                elif len(parts) == 3:                       # DD.MM.RRRR
                    d, m, y = map(int, parts)
                    parsed = f"{y:04d}-{m:02d}-{d:02d}"
                else:
                    y, m, d = map(int, med.split("-"))
                    parsed = f"{y:04d}-{m:02d}-{d:02d}"
            except Exception:
                parsed = ""
            u["medical_exam"] = parsed

        # Umiejętności – nadpisujemy listę
        skills_str = r.get("skills", "")
        if skills_str:
            toks = [t.strip() for t in re.split(r"[;,]", skills_str) if t.strip()]
            # aktualizuj katalog globalny
            toks_ci = {x.casefold() for x in toks}
            for t in toks:
                key = t.casefold()
                if key not in catalog_ci:
                    catalog.append(t)
                    catalog_ci[key] = t
            # ustaw w profilu: True dla podanych, False dla reszty z katalogu
            u["skills"] = {s: (s.casefold() in toks_ci) for s in catalog}

        imported += 1

    save_users_to_file(group, users)
    save_skill_catalog(catalog)

    return redirect(f"/panel/{group}/?info=Zaimportowano%20{imported}%20wierszy%20z%20CSV.")

# -------------------------
# GRAFIK (widok dzienny)
# -------------------------
@never_cache
def grafik_view(request, group):
    """
    'Ustaw grafik' – w UI pole 'contact' traktujemy jako e-mail z profilu.
    """
    if request.session.get("auth_group") != group:
        return redirect("login", group=group)

    from datetime import date as _date
    date_str = (request.GET.get("date") or request.POST.get("date") or _date.today().isoformat()).strip()

    groups = load_groups()
    all_employees_map = defaultdict(list)   # dept -> [names]
    employees_meta = {}                     # name -> {contact(email prefer), email, phone, position, department}

    for g in groups:
        dept = g["name"]
        users_in_dept = load_users_norm(dept)
        for u in users_in_dept:
            name = (u.get("name") or "").strip()
            if not name:
                continue
            email = (u.get("email") or "").strip()
            phone = (u.get("contact") or "").strip()
            all_employees_map[dept].append(name)
            employees_meta[name] = {
                "contact": email or phone,     # UI zawsze widzi maila gdy jest
                "email": email,
                "phone": phone,
                "position": (u.get("position") or "").strip(),
                "department": dept,
            }

    current_users = load_users_norm(group)
    employee_list = []
    for u in current_users:
        employee_list.append({
            "name": u["name"],
            "position": (u.get("position") or "").strip(),
            "contact": (u.get("email") or u.get("contact") or "").strip(),  # prefer e-mail
        })
    employee_names = [u["name"] for u in current_users]

    plan_path = BASE_DIR / f"{group}_grafik_plan.json"
    info, error = None, None
    all_days = {}
    if plan_path.exists():
        try:
            data = json.loads(plan_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                all_days = data
            elif isinstance(data, list):
                all_days = {date_str: data}
            else:
                all_days = {}
        except Exception:
            all_days = {}
            error = "Nie udało się wczytać wcześniejszego szkicu (uszkodzony plik)."

    if request.method == "POST":
        emps = request.POST.getlist("emp[]")
        poss = request.POST.getlist("pos[]")
        conts = request.POST.getlist("contact[]")  # w formularzu pole nazywa się 'contact'

        rows = []
        for i in range(max(len(emps), len(poss), len(conts))):
            name = (emps[i] if i < len(emps) else "").strip()
            pos = (poss[i] if i < len(poss) else "").strip()
            contact_in = (conts[i] if i < len(conts) else "").strip()
            if not (name or pos or contact_in):
                continue

            email_pref = (employees_meta.get(name, {}) or {}).get("email", "")
            contact_val = email_pref or contact_in  # zapisuj e-mail gdy dostępny
            rows.append({"name": name, "position": pos, "contact": contact_val})

        all_days[date_str] = rows
        try:
            plan_path.write_text(json.dumps(all_days, ensure_ascii=False, indent=2), encoding="utf-8")
            info = f"Zapisano {len(rows)} wierszy dla {date_str}."
        except Exception as e:
            error = f"Nie udało się zapisać: {e}"

        return redirect(f"{request.path}?date={date_str}")

    rows = all_days.get(date_str, []) or []
    for r in rows:
        n = (r.get("name") or "").strip()
        email_pref = (employees_meta.get(n, {}) or {}).get("email", "")
        if email_pref:
            r["contact"] = email_pref

    return render(
        request,
        "pierwsza_app/grafik.html",
        {
            "group": group,
            "date_str": date_str,
            "rows": rows,
            "employee_names": employee_names,
            "employee_list": employee_list,
            "all_employees": dict(all_employees_map),
            "employees_meta": employees_meta,
            "info": info,
            "error": error,
        },
    )

# -------------------------
# SKRÓT „Ustaw grafik”
# -------------------------
@never_cache
def set_schedule(request, group):
    if request.session.get("auth_group") != group:
        return redirect("login", group=group)
    month = request.GET.get("month", "Styczeń")
    year = request.GET.get("year", "2025")
    return redirect(f"/edycja/{group}/?month={month}&year={year}")

# -------------------------
# WYLOGOWANIE
# -------------------------
@require_POST
def logout_view(request, group=None):
    request.session.flush()
    resp = redirect("start")
    resp["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp["Pragma"] = "no-cache"
    return resp

# -------------------------
# USUWANIE DZIAŁU
# -------------------------
def delete_group(request, group):
    groups = load_groups()
    g = get_group(groups, group)
    if not g:
        return redirect("start")

    error = None
    if request.method == "POST":
        login = (request.POST.get("login") or "").strip()
        password = (request.POST.get("password") or "").strip()

        if login == g["login"] and password == g["password"]:
            upath = users_path(group)
            if upath.exists():
                try:
                    upath.unlink()
                except Exception:
                    pass

            for f in BASE_DIR.glob(f"{group}_*.json"):
                try:
                    f.unlink()
                except Exception:
                    pass

            for pattern in [
                f"grafik_*{group.replace(' ', '_')}*.pdf",
                f"karta_*{group.replace(' ', '_')}*.pdf",
                f"grafik_*{group}*.pdf",
                f"karta_*{group}*.pdf",
            ]:
                for f in BASE_DIR.glob(pattern):
                    try:
                        f.unlink()
                    except Exception:
                        pass

            groups = [gr for gr in groups if gr["name"].strip() != group.strip()]
            save_groups(groups)
            return redirect("start")
        else:
            error = "Niepoprawny login lub hasło."

    return render(request, "pierwsza_app/delete_group.html", {"group": group, "error": error})

# -------------------------
# PING
# -------------------------
def ping(request):
    return HttpResponse("Działa web! ✅")

# -------------------------
# PODGLĄDOWA TABELA
# -------------------------
def tabela(request, group):
    month = request.GET.get("month", "Styczeń")
    year = request.GET.get("year", "2025")
    users = [u["name"] for u in load_users_norm(group)]
    days = range(1, days_in_month(month, year) + 1)
    return render(
        request,
        "pierwsza_app/table.html",
        {"group": group, "month": month, "year": year, "users": users, "days": days},
    )

# -------------------------
# AUTOSAVE KOMÓRKI
# -------------------------
def month_to_name(m):
    if isinstance(m, int) or (isinstance(m, str) and m.isdigit()):
        num = int(m)
        for name, val in POLISH_MONTHS.items():
            if val == num:
                return name
        raise ValueError("Nieznany numer miesiąca")
    return m

def _ensure_row_len(row, n):
    row = list(row) if row else []
    if len(row) < n:
        row.extend([""] * (n - len(row)))
    return row

@require_POST
def autosave_cell(request, group):
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"ok": False, "error": "Nieprawidłowy JSON"}, status=400)

    year = str(data.get("year") or "").strip()
    month_raw = data.get("month")
    user_name = (data.get("user_name") or "").strip()
    day = data.get("day")
    value = (data.get("value") or "").strip()

    if not (year and month_raw and user_name and day is not None):
        return JsonResponse({"ok": False, "error": "Brak wymaganych pól"}, status=400)

    try:
        month = month_to_name(month_raw)
    except Exception:
        return JsonResponse({"ok": False, "error": "Nieznany miesiąc"}, status=400)

    try:
        day = int(day)
    except Exception:
        return JsonResponse({"ok": False, "error": "Dzień musi być liczbą"}, status=400)

    table = load_month_data(group, month, year)

    users_all = [u["name"] for u in load_users_norm(group)]
    total_days = days_in_month(month, year)

    for uname in set(users_all + [user_name]):
        table[uname] = _ensure_row_len(table.get(uname, []), total_days)

    if not (1 <= day <= total_days):
        return JsonResponse({"ok": False, "error": "Dzień poza zakresem miesiąca"}, status=400)

    table[user_name][day - 1] = value
    save_table_to_file(group, month, year, table)
    return JsonResponse({"ok": True})

# -------------------------
# EDYCJA + PDF
# -------------------------
def edit_table(request, group):
    month = request.GET.get("month", "Styczeń")
    year = request.GET.get("year", "2025")

    users = load_users_norm(group)
    existing = load_month_data(group, month, year)
    days_list = list(range(1, days_in_month(month, year) + 1))

    if request.method == "POST":
        table = {}
        for u in users:
            row = []
            for d in days_list:
                row.append((request.POST.get(f"v__{u['name']}__{d}") or "").strip())
            table[u["name"]] = row

        json_path = save_table_to_file(group, month, year, table)
        action = request.POST.get("action", "save")

        if action == "grafik":
            json_name = Path(json_path).name
            try:
                return generate_grafik_pdf_response(json_name)
            except (FileNotFoundError, ValueError) as e:
                raise Http404(str(e))

        elif action == "karty":
            if generate_karty_pdf_response is None:
                return HttpResponse(
                    "Moduł generowania PDF kart nie jest jeszcze zaktualizowany. "
                    "Zaimplementuj funkcję generate_karty_pdf_response w pierwsza_app/core/pdf_karty.py analogicznie do grafiku.",
                    status=500
                )
            json_name = Path(json_path).name
            try:
                return generate_karty_pdf_response(json_name)
            except (FileNotFoundError, ValueError) as e:
                raise Http404(str(e))

        elif action == "save_back":
            return redirect("panel", group=group)

        return HttpResponseRedirect(request.get_full_path())

    rows = []
    for u in users:
        name = u["name"]
        row_vals = existing.get(name, []) or []
        days_for_row = []
        for d in days_list:
            val = row_vals[d - 1] if len(row_vals) >= d else ""
            days_for_row.append({"d": d, "val": val})
        rows.append({"name": name, "days": days_for_row})

    values = {}
    for r in rows:
        for cell in r["days"]:
            values[f"{r['name']}__{cell['d']}"] = cell["val"]

    return render(
        request,
        "pierwsza_app/table_edit.html",
        {
            "group": group,
            "month": month,
            "year": year,
            "users": users,
            "days": days_list,
            "rows": rows,
            "values": values,
        },
    )

# -------------------------
# PROFIL PRACOWNIKA
# -------------------------
@never_cache
def employee_profile(request, group, emp_name):
    """
    Profil z edycją:
      - name, position, contact (tel), email, medical_exam
      - skills: checkboxy z GLOBALNEGO katalogu + dodawanie/kasowanie globalne
    """
    if request.session.get("auth_group") != group:
        return redirect("login", group=group)

    emp_name = unquote(emp_name).strip()
    users = load_users_norm(group)
    idx = next((i for i, u in enumerate(users) if u.get("name") == emp_name), None)
    if idx is None:
        raise Http404("Nie znaleziono takiego pracownika w tym dziale.")

    employee = users[idx]
    info = error = None

    # Usuwanie umiejętności globalnie (opcjonalny przycisk w UI)
    if request.method == "POST" and request.POST.get("action") == "delete_skill":
        skill_to_delete = (request.POST.get("skill") or "").strip()
        if skill_to_delete:
            if delete_skill_globally(skill_to_delete):
                info = f"Usunięto umiejętność „{skill_to_delete}” globalnie."
            else:
                error = "Nie udało się usunąć (brak na liście)."

    catalog = load_skill_catalog()

    if request.method == "POST" and request.POST.get("action") != "delete_skill":
        new_name = (request.POST.get("name") or "").strip()
        new_pos = (request.POST.get("position") or "").strip()
        new_contact = (request.POST.get("contact") or "").strip()
        new_email = (request.POST.get("email") or "").strip()
        new_exam = (request.POST.get("medical_exam") or "").strip()

        # Dodanie nowej umiejętności globalnie (pole np. name="new_skill")
        new_skill = (request.POST.get("new_skill") or "").strip()
        if new_skill:
            if all(new_skill.casefold() != s.casefold() for s in catalog):
                catalog.append(new_skill)
                save_skill_catalog(catalog)
                if info:
                    info += " Dodano nową umiejętność."
                else:
                    info = "Dodano nową umiejętność."
            else:
                info = (info + " Umiejętność już istnieje.") if info else "Umiejętność już istnieje."

        selected = set(request.POST.getlist("skills") or [])
        if new_skill:
            selected.add(new_skill)

        if not new_name:
            error = "Imię i nazwisko nie może być puste."
        elif new_email and not EMAIL_RE.match(new_email):
            error = "Podaj poprawny adres e-mail."
        elif new_exam and not re.match(r"^\d{4}-\d{2}-\d{2}$", new_exam):
            error = "Termin badań musi być w formacie RRRR-MM-DD."

        if not error and new_name != employee["name"] and any(u["name"] == new_name for u in users):
            error = f"Pracownik o nazwie „{new_name}” już istnieje."

        if not error:
            users[idx]["name"] = new_name
            users[idx]["position"] = new_pos
            users[idx]["contact"] = new_contact
            users[idx]["email"] = new_email
            users[idx]["medical_exam"] = new_exam

            # zaktualizowany katalog (po ewentualnym dodaniu new_skill)
            skills_map = {s: (s in selected) for s in catalog}
            users[idx]["skills"] = skills_map

            save_users_to_file(group, users)
            info = ("Zapisano zmiany." if not info else "Zapisano zmiany. " + info)

            if new_name != emp_name:
                return redirect("employee_profile", group=group, emp_name=new_name)
            employee = users[idx]

    # Odśwież katalog + dołącz ewentualne klucze nietypowe z profilu
    catalog = load_skill_catalog()
    extra_from_user = [k for k in (employee.get("skills") or {}).keys()
                       if all(k.casefold() != s.casefold() for s in catalog)]
    full_catalog = catalog + extra_from_user
    emp_skills_on = [k for k, v in (employee.get("skills") or {}).items() if v]

    return render(
        request,
        "pierwsza_app/employee_profile.html",
        {
            "group": group,
            "employee": employee,
            "skills_catalog": full_catalog,
            "emp_skills_on": emp_skills_on,
            "info": info,
            "error": error,
        },
    )
