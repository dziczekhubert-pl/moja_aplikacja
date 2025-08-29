from django.shortcuts import render, redirect
from django.http import HttpResponse, FileResponse, HttpResponseRedirect, JsonResponse, Http404
from django.conf import settings
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache
from django.core.mail import send_mail, BadHeaderError  # <-- WAŻNE: import wysyłki maili
from pathlib import Path
from datetime import date, timedelta
from collections import defaultdict
from urllib.parse import unquote
import os
import json
import re

from .utils import (
    POLISH_MONTHS,
    load_groups, save_groups, get_group,
    users_path, load_users_from_file, save_users_to_file,
    load_month_data, save_table_to_file, days_in_month,
)

# katalog projektu (tam gdzie manage.py)
BASE_DIR = Path(settings.BASE_DIR)
SKILLS_FILE = BASE_DIR / "skills_catalog.json"

def load_skill_catalog():
    try:
        if SKILLS_FILE.exists():
            data = json.loads(SKILLS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                # zwracamy listę unikalnych, przyciętych nazw
                out = []
                seen = set()
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
    # porządkowanie + zapis
    uniq = []
    seen = set()
    for x in catalog or []:
        s = str(x).strip()
        k = s.casefold()
        if s and k not in seen:
            seen.add(k)
            uniq.append(s)
    SKILLS_FILE.write_text(json.dumps(uniq, ensure_ascii=False, indent=2), encoding="utf-8")

# --- IMPORTY PDF (nowy mechanizm: generowanie w pamięci) ---
from .core.pdf_grafik import generate_pdf_response as generate_grafik_pdf_response   # <- WYMAGANE

# Karty: spróbuj użyć nowej funkcji, ale jeśli jeszcze nie wdrożona, pokaż czytelny komunikat
try:
    from .core.pdf_karty import generate_karty_pdf_response  # <- ZAIMPLEMENTUJ analogicznie jak pdf_grafik
except Exception:
    generate_karty_pdf_response = None


# =======================
#  WYSYŁKA E-MAILI – tylko e-maile z profilu!
# =======================
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

@require_POST
@never_cache
def notify_email(request, group):
    """
    POST /grafik/<group>/notify-email/

    Body (JSON):
      {
        "subject": "...",            # opcjonalnie
        "message": "...",            # opcjonalnie
        "employees": ["Milena", ...] # OPCJONALNIE: wyślij tylko do tych osób (po 'name')
        "extra": ["a@b.com", ...]    # OPCJONALNIE: dodatkowe adresy poza profilami
      }

    ZAWSZE zbiera adresy z <group>_users.json -> pole 'email'.
    Pole 'recipients' (jeśli ktoś wyśle z frontu) jest IGNOROWANE.
    """
    if request.session.get("auth_group") != group:
        return JsonResponse({"ok": False, "detail": "Nie zalogowano do tego działu."}, status=401)

    # wczytaj JSON
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception as e:
        return JsonResponse({"ok": False, "detail": f"Nieprawidłowy JSON: {e}"}, status=400)

    subject = (data.get("subject") or f"Grafik {group}").strip()
    message = (data.get("message") or f"Został zaktualizowany grafik dla działu {group}.").strip()

    # 1) Wczytaj pracowników działu (z rozszerzonymi polami)
    users = load_users_norm(group)  # [{"name","position","contact","email","medical_exam","skills"}]

    # 2) Ewentualny filtr po nazwach
    only_names = set(data.get("employees") or []) if isinstance(data.get("employees"), list) else None

    # 3) Zbuduj listę odbiorców TYLKO z e-maili w profilach
    recipients = []
    missing_email_for = []  # nazwy osób bez e-maila, przydatne w odpowiedzi

    for u in users:
        if only_names and u.get("name") not in only_names:
            continue
        email = (u.get("email") or "").strip()
        if email and EMAIL_RE.match(email):
            recipients.append(email)
        else:
            if only_names:  # raportuj brak tylko dla żądanych
                missing_email_for.append(u.get("name") or "")

    # 4) Dodatkowe adresy (opcjonalnie)
    extras = data.get("extra") if isinstance(data.get("extra"), list) else []
    extras = [e.strip() for e in extras if isinstance(e, str) and EMAIL_RE.match(e.strip())]

    # 5) Deduplikacja
    recipients = sorted(set(recipients + extras))

    if not recipients:
        detail = "Brak poprawnych adresów e-mail w profilach."
        if missing_email_for:
            detail += f" Brak e-maili dla: {', '.join(missing_email_for)}."
        return JsonResponse({"ok": False, "detail": detail}, status=400)

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com")

    try:
        sent = send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=recipients,
            fail_silently=False,
        )
        # Zwrotnie raportujemy, DO KOGO poszło i kogo ominęło (bo brak e-maila)
        return JsonResponse({
            "ok": True,
            "sent": int(sent),
            "recipients": recipients,
            "missing_email_for": missing_email_for,
        })
    except BadHeaderError:
        return JsonResponse({"ok": False, "detail": "Nieprawidłowy nagłówek e-mail."}, status=400)
    except Exception as e:
        return JsonResponse({"ok": False, "detail": f"Błąd wysyłki: {e}"}, status=500)




# =======================
#  POMOCNICZE – USERS
# =======================
def normalize_users(users_list):
    """
    Zwraca listę słowników w formacie:
    {
      "name": "...",
      "position": "...",
      "contact": "...",   # telefon
      "email": "...",
      "medical_exam": "YYYY-MM-DD",
      "skills": { "<dowolna_nazwa>": bool, ... }
    }
    """
    norm = []
    for u in users_list or []:
        if isinstance(u, str):
            norm.append({
                "name": u, "position": "", "contact": "",
                "email": "", "medical_exam": "",
                "skills": {},
            })
        elif isinstance(u, dict):
            # wczytaj skills w elastycznej formie (dict lub lista)
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
                "medical_exam": (u.get("medical_exam") or "").strip(),
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
                if any(k not in x for k in ("contact", "position", "email", "medical_date", "skills")):
                    needs_migration = True
                    break

    if needs_migration:
        save_users_to_file(group, users)
    return users



# =======================
#   STRONA STARTOWA
# =======================
@never_cache
def start(request):
    """
    Lista działów + ukryty formularz dodawania nowego działu.
    """
    groups = load_groups()

    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        login = (request.POST.get("login") or "").strip()
        password = (request.POST.get("password") or "").strip()

        if not (name and login and password):
            return render(
                request,
                "pierwsza_app/start.html",
                {"groups": groups, "error": "Wypełnij wszystkie pola."}
            )

        if get_group(groups, name):
            return render(
                request,
                "pierwsza_app/start.html",
                {"groups": groups, "error": f"Dział „{name}” już istnieje."}
            )

        groups.append({"name": name, "login": login, "password": password})
        save_groups(groups)

        # utwórz pusty plik z pracownikami (jeśli go nie ma)
        if not users_path(name).exists():
            save_users_to_file(name, [])  # od razu w nowym formacie nic nie trzeba

        return redirect("login", group=name)

    return render(request, "pierwsza_app/start.html", {"groups": groups})


# =======================
#     LOGOWANIE DZIAŁU
# =======================
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

        # proste sprawdzenie (jeśli nie chcesz globalnego admina — usuń drugi warunek)
        if (login == g["login"] and password == g["password"]) or (login == "admin" and password == "admin"):
            # zapisz stan logowania w sesji dla danego działu
            request.session["auth_group"] = group
            return redirect("panel", group=group)
        error = "Niepoprawny login lub hasło."

    return render(request, "pierwsza_app/login.html", {"group": group, "error": error})


# =======================
#  POMOCNICZE DO PANELU
# =======================
def months_between(from_month, from_year, to_month, to_year):
    fm, fy = POLISH_MONTHS[from_month], int(from_year)
    tm, ty = POLISH_MONTHS[to_month], int(to_year)
    out = []
    y, m = fy, fm
    # nazwy miesięcy z mapy (odwrotne wyszukiwanie)
    num2name = {v: k for k, v in POLISH_MONTHS.items()}
    while (y < ty) or (y == ty and m <= tm):
        out.append((num2name[m], str(y)))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


# ======= ŚWIĘTA I NIEDZIELE =======
def _easter_date(y: int) -> date:
    """Data Wielkanocy (algorytm Meeusa)."""
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
    """Stałe święta + Pon. Wielkanocny + Boże Ciało."""
    fixed = {
        (1, 1), (1, 6),
        (5, 1), (5, 3),
        (8, 15),
        (11, 1), (11, 11),
        (12, 25), (12, 26),
    }
    if (m, d) in fixed:
        return True
    easter = _easter_date(y)
    easter_mon = easter + timedelta(days=1)
    corpus_christi = easter + timedelta(days=60)
    return (m, d) in {(easter_mon.month, easter_mon.day), (corpus_christi.month, corpus_christi.day)}


def _is_sunday_or_holiday(y: int, m: int, d: int) -> bool:
    """Niedziela (weekday==6) lub święto z listy powyżej."""
    try:
        wd = date(y, m, d).weekday()  # Mon=0 ... Sun=6
    except ValueError:
        return False
    return wd == 6 or _is_polish_holiday(y, m, d)


def count_stats(group, employees, month_year_list):
    """
    Zlicza:
      - 'ndz'      : ile razy wpisano 1/2/3 w dniu będącym niedzielą LUB świętem,
      - 'l4'       : ile razy wpisano 'C' (L4),
      - 'workdays' : ile razy wpisano 1/2/3 w dniu roboczym pn–sob (0..5) z wyłączeniem świąt i niedziel.
                     (Soboty wliczane – zgodnie z wymaganiem).
    """
    WORK_TOKENS = {"1", "2", "3"}

    stats = {e["name"]: {"ndz": 0, "l4": 0, "workdays": 0} for e in employees}

    for month_name, year_str in month_year_list:
        y = int(year_str)
        m = POLISH_MONTHS[month_name]  # 1..12
        n_days = days_in_month(month_name, year_str)
        data = load_month_data(group, month_name, year_str)  # {emp_name: [dni...]}

        for e in employees:
            row = data.get(e["name"], []) or []
            for d in range(1, n_days + 1):
                val = (row[d - 1] if len(row) >= d else "") or ""
                v = val.strip()
                # L4
                if v.upper() == "C":
                    stats[e["name"]]["l4"] += 1
                # Praca (1/2/3) – kwalifikacja dnia
                if v in WORK_TOKENS:
                    if _is_sunday_or_holiday(y, m, d):
                        stats[e["name"]]["ndz"] += 1
                    else:
                        wd = date(y, m, d).weekday()  # 0..6
                        # dni robocze pn–sob (0..5), święta już wykluczone
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
    # zmiana nazwy grupy w groups.json
    groups = load_groups()
    for g in groups:
        if g["name"].strip() == old.strip():
            g["name"] = new
    save_groups(groups)

    # przeniesienie pliku users
    old_users = users_path(old)
    new_users = users_path(new)
    if old_users.exists():
        old_users.rename(new_users)

    # przeniesienie plików miesięcznych
    for f in BASE_DIR.glob(f"{old}_*.json"):
        f.rename(BASE_DIR / f.name.replace(f"{old}_", f"{new}_"))


# =======================
#        PANEL
# =======================
@never_cache
def panel(request, group):
    """
    Pasek akcji (dodaj pracownika, rozlicz karty, zmień dane log., zmień nazwę działu),
    filtr „Szukaj”, zakres Od/Do i tabela ze statystykami + kolumna Akcja.
    """
    # Wymuś aktywną sesję dla tego działu
    if request.session.get("auth_group") != group:
        return redirect("login", group=group)

    users = load_users_norm(group)  # lista {"name","position","contact"}
    groups_all = [g["name"] for g in load_groups()]
    info, error = None, None

    # GET – filtr i zakres statystyk
    q = (request.GET.get("q") or "").strip()
    from_month = request.GET.get("from_month", "Styczeń")
    from_year = request.GET.get("from_year", "2025")
    to_month = request.GET.get("to_month", "Grudzień")
    to_year = request.GET.get("to_year", "2025")

    # filtrowanie listy
    visible_users = [u for u in users if q.lower() in u["name"].lower()] if q else users

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "add_employee":
            new_emp = (request.POST.get("new_emp") or "").strip()
            if new_emp:
                if not any(u["name"] == new_emp for u in users):
                    users.append({"name": new_emp, "position": "", "contact": ""})
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
            # NOWE: przycisk "Ustaw grafik" – przejście do edycji z wybranym miesiącem/rokiem
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

        # PRG – odśwież po POST
        return redirect("panel", group=group)

    # przygotuj dane do tabeli (statystyki liczymy tylko gdy kliknięto „Pokaż…”)
    table_rows = []
    if request.GET.get("action") == "show_stats":
        month_years = months_between(from_month, from_year, to_month, to_year)
        stats = count_stats(group, visible_users, month_years)
        for u in visible_users:
            table_rows.append({
    "name": u["name"],
    "position": u.get("position", ""),
    "contact": u.get("contact", ""),   # tel do wyświetlania
    "email": u.get("email", ""),       # <-- to będzie użyte w mailto
    "workdays": stats[u["name"]]["workdays"],
    "ndz": stats[u["name"]]["ndz"],
    "l4": stats[u["name"]]["l4"],
                }
            )
    else:
        for u in visible_users:
            table_rows.append({
    "name": u["name"],
    "position": u.get("position", ""),
    "contact": u.get("contact", ""),
    "email": u.get("email", ""),       # <-- to samo tutaj
    "workdays": 0, "ndz": 0, "l4": 0
            })

    months = list(POLISH_MONTHS.keys())
    years = [str(y) for y in range(2025, 2035)]

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


@never_cache
def grafik_view(request, group):
    """
    Zakładka 'Ustaw grafik' - plan dzienny z nawigacją poprzedni/następny/dziś.
    - GET: wczytuje stan dla wybranego dnia (?date=YYYY-MM-DD), domyślnie dziś
    - POST: zapisuje stan w kluczu wybranego dnia
    Format pliku: { "YYYY-MM-DD": [ {name, position, contact}, ... ], ... }

    ZMIANA: 'contact' w UI = E-MAIL z profilu (telefon trzymamy jako 'phone').
    """
    if request.session.get("auth_group") != group:
        return redirect("login", group=group)

    # 1) Data z query stringa -> default: dziś
    from datetime import date as _date
    date_str = (request.GET.get("date") or request.POST.get("date") or _date.today().isoformat()).strip()

    # 2) Zbierz WSZYSTKICH pracowników z WSZYSTKICH działów
    groups = load_groups()
    all_employees_map = defaultdict(list)   # dept -> [names]
    employees_meta = {}                     # name -> {email, phone, position, department, contact(=email)}

    for g in groups:
        dept = g["name"]
        users_in_dept = load_users_norm(dept)  # [{"name","position","contact","email",...}]
        for u in users_in_dept:
            name = (u.get("name") or "").strip()
            if not name:
                continue
            email = (u.get("email") or "").strip()
            phone = (u.get("contact") or "").strip()
            all_employees_map[dept].append(name)
            # Uwaga: 'contact' ustawiamy na E-MAIL, żeby UI zawsze widziało maila
            employees_meta[name] = {
                "contact": email or phone,     # <<<<<<<<<< kluczowe: kontakt = e-mail
                "email": email,
                "phone": phone,
                "position": (u.get("position") or "").strip(),
                "department": dept,
            }

    # Dla zgodności: lista użytkowników tylko bieżącego działu
    current_users = load_users_norm(group)
    # Podmień 'contact' na E-MAIL także tutaj (stare szablony używają employee_list)
    employee_list = []
    for u in current_users:
        employee_list.append({
            "name": u["name"],
            "position": (u.get("position") or "").strip(),
            "contact": (u.get("email") or u.get("contact") or "").strip(),  # << mail
        })
    employee_names = [u["name"] for u in current_users]

    # 3) Wczytaj cały słownik planów (per-day)
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

    # 4) POST: zapisz rows dla bieżącego date_str
    if request.method == "POST":
        emps = request.POST.getlist("emp[]")
        poss = request.POST.getlist("pos[]")
        conts = request.POST.getlist("contact[]")  # w formularzu dalej 'contact', ale my wstawimy tam e-mail

        rows = []
        for i in range(max(len(emps), len(poss), len(conts))):
            name = (emps[i] if i < len(emps) else "").strip()
            pos = (poss[i] if i < len(poss) else "").strip()
            contact_in = (conts[i] if i < len(conts) else "").strip()

            if not (name or pos or contact_in):
                continue

            # jeżeli wprowadzono nazwę pracownika, preferuj e-mail z profilu
            email_pref = (employees_meta.get(name, {}) or {}).get("email", "")
            contact_val = email_pref or contact_in  # zapisuj e-mail gdy dostępny

            rows.append({"name": name, "position": pos, "contact": contact_val})

        # zaktualizuj słownik i zapisz
        all_days[date_str] = rows
        try:
            with plan_path.open("w", encoding="utf-8") as f:
                json.dump(all_days, f, ensure_ascii=False, indent=2)
            info = f"Zapisano {len(rows)} wierszy dla {date_str}."
        except Exception as e:
            error = f"Nie udało się zapisać: {e}"

        return redirect(f"{request.path}?date={date_str}")

    # 5) GET: rows dla wybranej daty
    rows = all_days.get(date_str, []) or []

    # Nadpisz pole 'contact' e-mailem z profilu (jeśli istnieje), żeby na widoku był mail, nie telefon
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

            # Stare klucze (dla zgodności ze starym templatem)
            "employee_names": employee_names,
            "employee_list": employee_list,       # tu 'contact' = e-mail

            # NOWE – pełna lista i meta (tu 'contact' = e-mail)
            "all_employees": dict(all_employees_map),
            "employees_meta": employees_meta,

            "info": info,
            "error": error,
        },
    )


# =======================
#  USTAW GRAFIK (skrót)
# =======================
@never_cache
def set_schedule(request, group):
    """
    Skrót pod przycisk „Ustaw grafik”.
    Kontrola sesji + przekierowanie do edycji z podanym miesiącem/rokiem (GET lub domyślne).
    """
    if request.session.get("auth_group") != group:
        return redirect("login", group=group)

    # Przyjmij miesiąc/rok z query stringa (jeśli klik na link) lub domyślne.
    month = request.GET.get("month", "Styczeń")
    year = request.GET.get("year", "2025")
    return redirect(f"/edycja/{group}/?month={month}&year={year}")


# =======================
#      WYLOGOWANIE
# =======================
@require_POST
def logout_view(request, group=None):
    """
    Czyści sesję i wraca na stronę startową. Dodaje nagłówki anty-cache.
    """
    request.session.flush()
    resp = redirect("start")
    resp["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp["Pragma"] = "no-cache"
    return resp


# =======================
#      USUWANIE DZIAŁU
# =======================
def delete_group(request, group):
    """
    Usuwa dział po podaniu poprawnego loginu/hasła:
    - usuwa wpis z groups.json,
    - kasuje <Grupa>_users.json,
    - kasuje <Grupa>_<Miesiąc>_<Rok>.json,
    - usuwa ewentualne PDF-y (grafik/karty).
    """
    groups = load_groups()
    g = get_group(groups, group)
    if not g:
        return redirect("start")

    error = None

    if request.method == "POST":
        login = (request.POST.get("login") or "").strip()
        password = (request.POST.get("password") or "").strip()

        if login == g["login"] and password == g["password"]:

            # users.json
            upath = users_path(group)
            if upath.exists():
                try:
                    upath.unlink()
                except Exception:
                    pass

            # miesięczne JSON-y
            for f in BASE_DIR.glob(f"{group}_*.json"):
                try:
                    f.unlink()
                except Exception:
                    pass

            # PDF-y (różne warianty nazw)
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

            # usuń dział z groups.json
            groups = [gr for gr in groups if gr["name"].strip() != group.strip()]
            save_groups(groups)
            return redirect("start")
        else:
            error = "Niepoprawny login lub hasło."

    return render(request, "pierwsza_app/delete_group.html", {"group": group, "error": error})


# =======================
#    TEST / PING
# =======================
def ping(request):
    return HttpResponse("Działa web! ✅")


# =======================
#   PODGLĄDOWA TABELA
# =======================
def tabela(request, group):
    month = request.GET.get("month", "Styczeń")
    year = request.GET.get("year", "2025")
    # przekaż listę nazw (jeśli stary szablon tego oczekuje)
    users = [u["name"] for u in load_users_norm(group)]
    days = range(1, days_in_month(month, year) + 1)
    return render(
        request,
        "pierwsza_app/table.html",
        {"group": group, "month": month, "year": year, "users": users, "days": days},
    )


# =======================
#   AUTOSAVE POJEDYNCZEJ KOMÓRKI
# =======================
def month_to_name(m):
    """
    Przyjmuje np. 'Sierpień' lub 8 / '8' i zwraca nazwę miesiąca zgodną z plikami JSON.
    """
    if isinstance(m, int) or (isinstance(m, str) and m.isdigit()):
        num = int(m)
        for name, val in POLISH_MONTHS.items():
            if val == num:
                return name
        raise ValueError("Nieznany numer miesiąca")
    return m


def _ensure_row_len(row, n):
    """Upewnij się, że lista ma długość n (dopaduj '' gdy brakuje)."""
    row = list(row) if row else []
    if len(row) < n:
        row.extend([""] * (n - len(row)))
    return row


@require_POST
def autosave_cell(request, group):
    """
    Zapis pojedynczej komórki do JSON:
    body JSON: { "year": "2025", "month": "Sierpień" | 8, "user_name": "...", "day": 1..31, "value": "..." }
    """
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

    # wczytaj aktualny JSON
    table = load_month_data(group, month, year)  # {name: [dni...]}

    # upewnijmy się, że istnieją wiersze dla wszystkich pracowników (w tym tego edytowanego)
    users_all = [u["name"] for u in load_users_norm(group)]
    total_days = days_in_month(month, year)

    for uname in set(users_all + [user_name]):
        table[uname] = _ensure_row_len(table.get(uname, []), total_days)

    # walidacja zakresu dnia
    if not (1 <= day <= total_days):
        return JsonResponse({"ok": False, "error": "Dzień poza zakresem miesiąca"}, status=400)

    # ustaw komórkę (1-index → lista 0-index)
    table[user_name][day - 1] = value

    # zapisz cały miesiąc z powrotem
    save_table_to_file(group, month, year, table)

    return JsonResponse({"ok": True})


# =======================
#  EDYCJA + ZAPIS + PDF
# =======================
def edit_table(request, group):
    month = request.GET.get("month", "Styczeń")
    year = request.GET.get("year", "2025")

    users = load_users_norm(group)                  # lista dictów {"name","position","contact"}
    existing = load_month_data(group, month, year)  # {name: [dni...]}
    days_list = list(range(1, days_in_month(month, year) + 1))

    if request.method == "POST":
        # zbierz dane z formularza
        table = {}
        for u in users:
            row = []
            for d in days_list:
                row.append((request.POST.get(f"v__{u['name']}__{d}") or "").strip())
            table[u["name"]] = row

        # zapisz JSON
        json_path = save_table_to_file(group, month, year, table)  # może zwrócić Path lub string

        action = request.POST.get("action", "save")

        if action == "grafik":
            # Użyj nowego generatora PDF w pamięci.
            # Podajemy NAZWĘ pliku (relative do BASE_DIR), bo tak oczekuje helper.
            json_name = Path(json_path).name
            try:
                return generate_grafik_pdf_response(json_name)
            except (FileNotFoundError, ValueError) as e:
                raise Http404(str(e))

        elif action == "karty":
            if generate_karty_pdf_response is None:
                return HttpResponse(
                    "Moduł generowania PDF kart nie jest jeszcze zaktualizowany. "
                    "Zaimplementuj funkcję generate_karty_pdf_response w pierwsza_app/core/pdf_karty.py "
                    "analogicznie do grafiku.",
                    status=500
                )
            json_name = Path(json_path).name
            try:
                return generate_karty_pdf_response(json_name)
            except (FileNotFoundError, ValueError) as e:
                raise Http404(str(e))

        elif action == "save_back":
            # zapis był wykonany powyżej → wracamy do panelu
            return redirect("panel", group=group)

        # domyślnie: zapis i zostajemy na stronie (PRG)
        return HttpResponseRedirect(request.get_full_path())

    # ===== GET – przygotuj DWA formaty danych, żeby każdy szablon zadziałał =====
    # 1) 'rows' (dla nowego szablonu: pętla po r in rows -> r.days)
    rows = []
    for u in users:
        name = u["name"]
        row_vals = existing.get(name, []) or []
        days_for_row = []
        for d in days_list:
            val = row_vals[d - 1] if len(row_vals) >= d else ""
            days_for_row.append({"d": d, "val": val})
        rows.append({"name": name, "days": days_for_row})

    # 2) 'values' (dla starego szablonu: values["Imię Nazwisko__d"])
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
            "users": users,     # jeśli szablon iteruje po users
            "days": days_list,  # nagłówki dni
            "rows": rows,       # jeśli szablon iteruje po rows
            "values": values,   # jeśli szablon korzysta z values[...] (stara wersja)
        },
    )


# =======================
#  PROFIL PRACOWNIKA
# =======================
SKILLS_CATALOG = [
    "kartoniarka",
    "krajalnica",
    "vacuum",
    "paletyzer",
]

@never_cache
def employee_profile(request, group, emp_name):
    """
    Profil pracownika z edycją:
      - name, position, contact (tel), email, medical_exam
      - skills: checkboxy z GLOBALNEGO katalogu + dodawanie nowej umiejętności (globalnie)
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

    # Załaduj katalog globalny
    catalog = load_skill_catalog()

    if request.method == "POST":
        new_name = (request.POST.get("name") or "").strip()
        new_pos = (request.POST.get("position") or "").strip()
        new_contact = (request.POST.get("contact") or "").strip()
        new_email = (request.POST.get("email") or "").strip()
        new_exam = (request.POST.get("medical_exam") or "").strip()

        # Nowa umiejętność (globalna)
        new_skill = (request.POST.get("new_skill") or "").strip()
        if new_skill:
            # dodaj do katalogu globalnego, jeśli nie ma (case-insensitive)
            if all(new_skill.casefold() != s.casefold() for s in catalog):
                catalog.append(new_skill)
                save_skill_catalog(catalog)
                info = "Dodano nową umiejętność do katalogu globalnego."
            else:
                info = "Umiejętność już istnieje w katalogu."

        # zaznaczone umiejętności (checkbox name="skills" value="<nazwa>")
        selected = set(request.POST.getlist("skills") or [])
        # Jeśli dodano nową umiejętność – automatycznie ją zaznacz dla tego pracownika
        if new_skill:
            selected.add(new_skill)

        # prosta walidacja pól kontaktowych
        if not new_name:
            error = "Imię i nazwisko nie może być puste."
        elif new_email and not EMAIL_RE.match(new_email):
            error = "Podaj poprawny adres e-mail."
        elif new_exam and not re.match(r"^\d{4}-\d{2}-\d{2}$", new_exam):
            error = "Termin badań musi być w formacie RRRR-MM-DD."

        if not error and new_name != employee["name"] and any(u["name"] == new_name for u in users):
            error = f"Pracownik o nazwie „{new_name}” już istnieje."

        if not error:
            # Zapis pól prostych
            users[idx]["name"] = new_name
            users[idx]["position"] = new_pos
            users[idx]["contact"] = new_contact
            users[idx]["email"] = new_email
            users[idx]["medical_exam"] = new_exam

            # Zapis umiejętności: mapowanie katalog -> bool (zaznaczony czy nie)
            # UWAGA: używamy aktualnego katalogu (już po ewentualnym dodaniu new_skill)
            skills_map = {}
            for s in catalog:
                skills_map[s] = (s in selected)
            users[idx]["skills"] = skills_map

            save_users_to_file(group, users)
            if info:
                info = "Zapisano zmiany. " + info
            else:
                info = "Zapisano zmiany."

            # jeżeli zmieniono nazwę – przekieruj, by adres URL pasował
            if new_name != emp_name:
                return redirect("employee_profile", group=group, emp_name=new_name)
            employee = users[idx]

    # (GET lub po POST) – odśwież employee i katalog (gdyby był dodany)
    catalog = load_skill_catalog()
    # Upewnij się, że pokażemy też ewentualne „stare” umiejętności, które nie były jeszcze w katalogu
    extra_from_user = [k for k in (employee.get("skills") or {}).keys()
                       if all(k.casefold() != s.casefold() for s in catalog)]
    full_catalog = catalog + extra_from_user  # kolejność: katalog -> ewentualne dodatkowe klucze użytkownika

    # Lista „włączonych” umiejętności dla szablonu (łatwiej zaznaczyć checkboxy)
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