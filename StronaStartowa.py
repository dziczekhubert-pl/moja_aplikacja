import RozliczKarty2
import RozliczKarty3
import tkinter as tk
from tkinter import ttk, messagebox
import calendar
import json
import os
import subprocess
import glob  # <-- do wyszukiwania plików JSON

# ===================== KONFIGURACJA =====================
ADMIN_LOGIN = "admin"
ADMIN_PASSWORD = "admin"

# ===================== FUNKCJE POMOCNICZE =====================


def safe_destroy(widget):
    """Bezpiecznie niszczy widget, o ile ten jeszcze istnieje."""
    try:
        if widget is not None and widget.winfo_exists():
            widget.destroy()
    except tk.TclError as e:
        if "application has been destroyed" in str(e):
            pass
        else:
            raise


# ===================== ZAPIS I ODCZYT GRUP =====================
SAVE_FILE = "groups.json"

# Globalna lista grup – każda grupa to słownik:
# {"name": ..., "login": ..., "password": ..., "frame": ...}
groups = []


def load_groups():
    if os.path.exists(SAVE_FILE):
        with open(SAVE_FILE, "r", encoding="utf-8") as file:
            try:
                return json.load(file)
            except Exception as e:
                print("Błąd odczytu grup:", e)
    return []


def save_groups():
    # Zapisujemy tylko dane (bez odnośników do widgetów Tkinter)
    data_to_save = [
        {"name": grp["name"].strip(), "login": grp["login"],
         "password": grp["password"]}
        for grp in groups
    ]
    with open(SAVE_FILE, "w", encoding="utf-8") as file:
        json.dump(data_to_save, file, ensure_ascii=False, indent=4)


def get_group_by_name(name):
    name = name.strip()
    for g in groups:
        if g["name"].strip() == name:
            return g
    return None

# ===================== FUNKCJE DO GENEROWANIA I OBSŁUGI TABEL =====================


def load_users_from_file(data_file):
    try:
        with open(data_file, "r", encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_table_to_file(data_file, month, year, table_entries):
    polish_months = {
        "Styczeń": 1, "Luty": 2, "Marzec": 3, "Kwiecień": 4, "Maj": 5, "Czerwiec": 6,
        "Lipiec": 7, "Sierpień": 8, "Wrzesień": 9, "Październik": 10, "Listopad": 11, "Grudzień": 12
    }
    group_name = data_file.replace("_users.json", "")
    month_number = polish_months[month]

    table_data = {}
    for entry in table_entries:
        table_data[entry["name"]] = [e.get() for e in entry["values"]]

    file_name = f"{group_name}_{month}_{year}.json"

    try:
        with open(file_name, "w", encoding="utf-8") as file:
            json.dump({"group": group_name, "month": month, "year": year,
                       "data": table_data}, file, ensure_ascii=False, indent=4)
        print(f"Tabela zapisana w pliku {file_name}")
    except Exception as e:
        print(f"Błąd podczas zapisywania tabeli: {e}")
    return file_name  # zwracamy nazwę zapisanego pliku


def recalc_counters(row_data):
    """Funkcja zliczająca X, Xz, W, 3, Nd w pojedynczym wierszu (nie dotyczy nowego licznika 'C' globalnie)."""
    count_X = 0
    count_Xz = 0
    count_W = 0
    count_3 = 0
    count_Nd = 0  # licznik dla Nd w polach z czerwonym tłem

    for i, entry in enumerate(row_data["values"]):
        value = entry.get().strip().lower()
        if value == "x":
            count_X += 1
        if value == "xz":
            count_Xz += 1
        if value == "w":
            count_W += 1
        if value == "3":
            count_3 += 1

        # Jeżeli dany dzień jest świętem lub niedzielą (bg="red") i wpis to 1/2/3:
        if row_data["bg_colors"][i] == "red" and value in ["1", "2", "3"]:
            count_Nd += 1

    if "label_X" in row_data:
        row_data["label_X"].config(text=str(count_X))
    if "label_Xz" in row_data:
        row_data["label_Xz"].config(text=str(count_Xz))
    if "label_W" in row_data:
        row_data["label_W"].config(text=str(count_W))
    if "label_3ki" in row_data:
        row_data["label_3ki"].config(text=str(count_3))
    if "label_Nd" in row_data:
        row_data["label_Nd"].config(text=str(count_Nd))


def open_table_window(data_file, month, year, table_data=None):
    users = load_users_from_file(data_file)

    polish_months = {
        "Styczeń": 1, "Luty": 2, "Marzec": 3, "Kwiecień": 4, "Maj": 5, "Czerwiec": 6,
        "Lipiec": 7, "Sierpień": 8, "Wrzesień": 9, "Październik": 10, "Listopad": 11, "Grudzień": 12
    }
    month_number = polish_months[month]
    days_in_month = calendar.monthrange(int(year), month_number)[1]

    group_name_local = data_file.replace("_users.json", "")
    file_name = f"{group_name_local}_{month}_{year}.json"
    if os.path.exists(file_name):
        try:
            with open(file_name, "r", encoding="utf-8") as file:
                table_data = json.load(file).get("data", {})
        except Exception as e:
            print(f"Błąd podczas wczytywania danych tabeli: {e}")
            table_data = {}

    window = tk.Toplevel()
    window.title(f"{month} {year}")

    # Ustawienie okna na pełną szerokość ekranu
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    window.geometry(f"{screen_width}x{screen_height}")

    # Górna ramka z nagłówkiem i przyciskami
    top_frame = tk.Frame(window)
    top_frame.pack(side=tk.TOP, fill=tk.X)

    header_label = tk.Label(
        top_frame, text=f"{month} {year}", font=("Arial", 16, "bold"), pady=10)
    header_label.pack(side=tk.LEFT, expand=True)

    button_frame = tk.Frame(window)
    button_frame.pack(side=tk.TOP)

    # Przycisk "Przejdź do drukowania"
    print_button = tk.Button(
        button_frame,
        text="Drukuj grafik",
        font=("Arial", 10),
        command=lambda: [
            save_table_to_file(data_file, month, year, table_entries),
            subprocess.Popen(["python", "RozliczKarty2.py", file_name])
        ]
    )
    print_button.pack(side=tk.LEFT, padx=10)

    # Przycisk "Drukuj karty pracy"
    drukuj_button = tk.Button(
        button_frame,
        text="Drukuj karty pracy",
        font=("Arial", 10),
        command=lambda: [
            save_table_to_file(data_file, month, year, table_entries),
            subprocess.Popen(["python", "RozliczKarty3.py", file_name])
        ]
    )
    drukuj_button.pack(side=tk.LEFT, padx=10)

    # Ramka z przewijaniem
    canvas = tk.Canvas(window)
    scroll_y = tk.Scrollbar(window, orient="vertical", command=canvas.yview)
    scroll_frame = tk.Frame(canvas)

    scroll_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )

    canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
    canvas.configure(yscrollcommand=scroll_y.set)

    canvas.pack(side="left", fill="both", expand=True)
    scroll_y.pack(side="right", fill="y")

    # Budowa nagłówków tabeli
    headers = [
        "Lp.",
        "Nazwisko i imię"
    ] + [str(day) for day in range(1, days_in_month + 1)] + [
        "",
        "X",
        "Xz",
        "W",
        "Nd",
        "3ki"
    ]

    holidays = [
        "01-01", "06-01", "21-04", "01-05", "03-05", "19-06",
        "15-08", "01-11", "11-11", "12-25", "12-26"
    ]

    for col, header in enumerate(headers):
        if header == "Nazwisko i imię":
            width = 20
        elif header == "":
            tk.Label(
                scroll_frame,
                text="",
                relief="flat",
                borderwidth=0,
                width=5,
                font=("Arial", 11),
                bg=scroll_frame.cget("bg")
            ).grid(row=0, column=col, sticky="nsew")
            continue
        else:
            width = 25 if header == "Nazwisko i imię" else 3

        if header.isdigit():
            day = int(header)
            date_key = f"{day:02d}-{month_number:02d}"
            weekday = calendar.weekday(int(year), month_number, day)
            if date_key in holidays:
                bg_color = "red"
            elif weekday == 6:
                bg_color = "red"
            elif weekday == 5:
                bg_color = "green"
            else:
                bg_color = "white"
        else:
            bg_color = "white"

        tk.Label(
            scroll_frame,
            text=header,
            relief="solid",
            borderwidth=1,
            width=width,
            font=("Arial", 11),
            bg=bg_color
        ).grid(row=0, column=col, sticky="nsew")

    table_entries = []

    for row_num, user in enumerate(users, start=1):
        user_data = {
            "name": user,
            "values": [],
            "bg_colors": []
        }

        tk.Label(
            scroll_frame,
            text=row_num,
            relief="solid",
            borderwidth=1,
            width=3,
            anchor="center",
            font=("Arial", 11),
            bg="white"
        ).grid(row=row_num, column=0, sticky="nsew")

        tk.Label(
            scroll_frame,
            text=user,
            relief="solid",
            borderwidth=1,
            width=20,
            anchor="w",
            font=("Arial", 11),
            bg="white"
        ).grid(row=row_num, column=1, sticky="nsew")

        for col_num in range(2, len(headers)):
            header_text = headers[col_num]

            if header_text == "":
                continue

            if header_text.isdigit():
                day = int(header_text)
                date_key = f"{day:02d}-{month_number:02d}"
                weekday = calendar.weekday(int(year), month_number, day)
                if date_key in holidays or weekday == 6:
                    bg_color = "red"
                elif weekday == 5:
                    bg_color = "green"
                else:
                    bg_color = "white"
            else:
                bg_color = "white"

            if header_text in ["X", "Xz", "W", "3ki", "Nd"]:
                label = tk.Label(
                    scroll_frame,
                    relief="solid",
                    borderwidth=1,
                    width=3,
                    anchor="center",
                    font=("Arial", 11),
                    bg="lightgray"
                )
                label.grid(row=row_num, column=col_num, sticky="nsew")

                # Wstaw do user_data, aby móc liczyć "x", "xz" itd.
                if header_text == "X":
                    user_data["label_X"] = label
                elif header_text == "Xz":
                    user_data["label_Xz"] = label
                elif header_text == "W":
                    user_data["label_W"] = label
                elif header_text == "3ki":
                    user_data["label_3ki"] = label
                elif header_text == "Nd":
                    user_data["label_Nd"] = label

                label.config(text="0")
            else:
                entry = tk.Entry(
                    scroll_frame,
                    relief="solid",
                    borderwidth=1,
                    width=3,
                    justify="center",
                    font=("Arial", 11),
                    bg=bg_color
                )
                entry.grid(row=row_num, column=col_num, sticky="nsew")

                if table_data and user in table_data:
                    values = table_data[user]
                    idx = col_num - 2
                    if idx < len(values):
                        entry.insert(0, values[idx])

                user_data["values"].append(entry)
                user_data["bg_colors"].append(bg_color)

                entry.bind("<KeyRelease>", lambda e,
                           rd=user_data: recalc_counters(rd))

        table_entries.append(user_data)
        recalc_counters(user_data)

    def save_and_close():
        # 1) Zapis danych z tabeli
        save_table_to_file(data_file, month, year, table_entries)
        # 2) Zamknięcie okna
        window.destroy()

    # Rejestracja funkcji save_and_close pod zdarzenie zamknięcia okna
    window.protocol("WM_DELETE_WINDOW", save_and_close)

    return table_entries


def open_table_generator_window(group_name):
    """
    Okno umożliwiające wybór miesiąca i roku dla generowanej tabeli.
    Po kliknięciu przycisku "Generuj", otwiera się okno z tabelą.
    """
    data_file = f"{group_name.strip()}_users.json"
    gen_window = tk.Toplevel(root)
    gen_window.title(f"Wygeneruj grafik dla: {group_name.strip()}")
    gen_window.geometry("540x100")

    months = [
        "Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec",
        "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień"
    ]
    years = [str(year) for year in range(2025, 2030)]

    selected_month = tk.StringVar(value=months[0])
    selected_year = tk.StringVar(value=years[0])

    top_frame = tk.Frame(gen_window)
    top_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)

    tk.Label(top_frame, text="Wybierz miesiąc:", font=("Arial", 10))\
      .grid(row=0, column=0, padx=5, pady=5)
    month_menu = ttk.Combobox(
        top_frame, values=months, textvariable=selected_month, state="readonly", width=15)
    month_menu.grid(row=0, column=1, padx=5, pady=5)

    tk.Label(top_frame, text="Wybierz rok:", font=("Arial", 10))\
      .grid(row=0, column=2, padx=5, pady=5)
    year_menu = ttk.Combobox(
        top_frame, values=years, textvariable=selected_year, state="readonly", width=10)
    year_menu.grid(row=0, column=3, padx=5, pady=5)

    def generate_table():
        open_table_window(data_file, selected_month.get(), selected_year.get())
        safe_destroy(gen_window)

    generate_button = tk.Button(
        top_frame, text="Generuj", font=("Arial", 10),
        command=generate_table
    )
    generate_button.grid(row=0, column=4, padx=10, pady=5)

# ===================== FUNKCJA ZLICZANIA Nd i C DLA WYBRANEGO OKRESU =====================


def calculate_nd_c_for_user_in_period(group_name, user_name, start_month, start_year, end_month, end_year):
    """
    Zwraca krotkę (nd_sum, c_sum) dla danego użytkownika w wybranym przedziale (start, end).
    - nd_sum zlicza '1'/'2'/'3' w niedziele/święta,
    - c_sum zlicza wszystkie wpisy 'c' (niezależnie od dnia tygodnia).
    """
    polish_months = {
        "Styczeń": 1, "Luty": 2, "Marzec": 3, "Kwiecień": 4, "Maj": 5, "Czerwiec": 6,
        "Lipiec": 7, "Sierpień": 8, "Wrzesień": 9, "Październik": 10, "Listopad": 11, "Grudzień": 12
    }

    def to_tuple(m, r):
        return (int(r), polish_months[m])

    start_tuple = to_tuple(start_month, start_year)
    end_tuple = to_tuple(end_month, end_year)

    holidays = {
        "01-01", "06-01", "21-04", "01-05", "03-05", "19-06",
        "15-08", "01-11", "11-11", "12-25", "12-26"
    }

    nd_sum = 0
    c_sum = 0

    pattern = f"{group_name.strip()}_*.json"
    for file_name in glob.glob(pattern):
        try:
            with open(file_name, "r", encoding="utf-8") as f:
                table_obj = json.load(f)
                if not isinstance(table_obj, dict):
                    # Jeżeli to nie jest słownik, pomijamy
                    continue
        except:
            continue

        month = table_obj.get("month")
        year = table_obj.get("year")
        data = table_obj.get("data", {})

        if not month or not year or not data:
            continue

        current_tuple = to_tuple(month, year)
        if current_tuple < start_tuple or current_tuple > end_tuple:
            continue

        if user_name not in data:
            continue

        entries = data[user_name]
        month_number = polish_months[month]
        days_in_month = calendar.monthrange(int(year), month_number)[1]

        for day_idx in range(days_in_month):
            if day_idx >= len(entries):
                break
            entry_value = entries[day_idx].strip().lower()
            day_number = day_idx + 1
            date_key = f"{day_number:02d}-{month_number:02d}"
            weekday = calendar.weekday(int(year), month_number, day_number)

            # Zliczanie ND:
            if weekday == 6 or date_key in holidays:
                if entry_value in ["1", "2", "3"]:
                    nd_sum += 1

            # Zliczanie C (każda "c" wstawiona w polu, bez względu na dzień):
            if entry_value == "c":
                c_sum += 1

    return nd_sum, c_sum

# ===================== OKNO GRUPY (EDYCJA UŻYTKOWNIKÓW) =====================


def open_new_window(group_name):
    """
    Okno szczegółowe dla danej grupy, w którym można:
      - Dodawać, usuwać, edytować użytkowników
      - Przeorganizować kolejność
      - Uruchomić generator tabeli (Rozlicz karty pracy)
      - Zmienić dane logowania, nazwę grupy lub usunąć grupę.
      - Przenieść użytkownika do wybranej grupy.
      - Na górze (pod comboboxami Od... Do...) mamy ND i C w jednej tabeli – tak jak w załączonym obrazku.
    """
    generator_launched = False

    def open_work_cards():
        nonlocal generator_launched
        generator_launched = True
        open_table_generator_window(group_name)

    # Funkcja "go_back" wywoływana przy zamykaniu okna grupy – przywracamy główne okno
    def go_back():
        safe_destroy(new_window)
        if root.winfo_exists():
            root.deiconify()

    new_window = tk.Toplevel(root)
    new_window.title(f"Dział: {group_name.strip()}")
    new_window.geometry("900x600")
    new_window.protocol("WM_DELETE_WINDOW", go_back)

    data_file = f"{group_name.strip()}_users.json"

    # Funkcje pomocnicze dla zarządzania użytkownikami
    def save_users_to_file(users_list):
        with open(data_file, "w", encoding="utf-8") as file:
            json.dump(users_list, file, ensure_ascii=False, indent=4)

    def load_users_from_file_local(dfile):
        try:
            with open(dfile, "r", encoding="utf-8") as file:
                return json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    users = load_users_from_file_local(data_file)

    # -- Ramka główna z przewijaniem --
    canvas = tk.Canvas(new_window)
    scrollbar = tk.Scrollbar(
        new_window, orient="vertical", command=canvas.yview)
    scrollable_frame = tk.Frame(canvas)
    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )
    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    def _on_mousewheel(event):
        canvas.yview_scroll(-1 * int(event.delta / 120), "units")
    canvas.bind_all("<MouseWheel>", _on_mousewheel)

    # ---------- Górny panel (entry_frame) ----------
    entry_frame = tk.Frame(scrollable_frame)
    entry_frame.grid(row=0, column=0, columnspan=5, sticky="w", pady=10)

    entry = tk.Entry(entry_frame, width=30)
    entry.pack(side=tk.LEFT, padx=5)
    tk.Button(entry_frame, text="Dodaj pracownika", command=lambda: add_user())\
      .pack(side=tk.LEFT, padx=5)
    tk.Button(entry_frame, text="Rozlicz karty pracy", command=open_work_cards)\
      .pack(side=tk.LEFT, padx=5)

    tk.Label(entry_frame, text="    ").pack(side=tk.LEFT)

    tk.Button(entry_frame, text="Zmień dane logowania", command=lambda: change_group_credentials(group_name))\
      .pack(side=tk.LEFT, padx=5)
    tk.Button(entry_frame, text="Edytuj nazwę działu", command=lambda: change_group_name())\
      .pack(side=tk.LEFT, padx=5)
    tk.Button(entry_frame, text="Usuń dział", command=lambda: delete_group_logged())\
      .pack(side=tk.LEFT, padx=5)

    # ------ Sekcja wyboru zakresu (Od... Do...) ------
    months_pl = [
        "Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec",
        "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień"
    ]
    years_range = [str(y) for y in range(2025, 2035)]

    start_month_var = tk.StringVar(value=months_pl[0])
    start_year_var = tk.StringVar(value=years_range[0])
    end_month_var = tk.StringVar(value=months_pl[-1])
    end_year_var = tk.StringVar(value=years_range[-1])

    range_frame = tk.Frame(scrollable_frame)
    range_frame.grid(row=1, column=0, columnspan=5,
                     sticky="nw", padx=5, pady=5)

    tk.Label(range_frame, text="Od:").pack(side=tk.LEFT, padx=2)
    start_month_cb = ttk.Combobox(
        range_frame, values=months_pl, textvariable=start_month_var, width=9, state="readonly")
    start_month_cb.pack(side=tk.LEFT, padx=2)
    start_year_cb = ttk.Combobox(
        range_frame, values=years_range, textvariable=start_year_var, width=5, state="readonly")
    start_year_cb.pack(side=tk.LEFT, padx=2)

    tk.Label(range_frame, text="  Do:").pack(side=tk.LEFT, padx=2)
    end_month_cb = ttk.Combobox(
        range_frame, values=months_pl, textvariable=end_month_var, width=9, state="readonly")
    end_month_cb.pack(side=tk.LEFT, padx=2)
    end_year_cb = ttk.Combobox(range_frame, values=years_range,
                               textvariable=end_year_var, width=5, state="readonly")
    end_year_cb.pack(side=tk.LEFT, padx=2)

    # ---------- Tabela użytkowników dokładnie tak, jak w zrzucie ----------
    data_frame = tk.Frame(scrollable_frame)
    data_frame.grid(row=2, column=0, columnspan=5,
                    sticky="nsew", padx=10, pady=10)

    # Słownik: user_nd_c = { user_name: (nd_value, c_value) }
    user_nd_c = {}

    def update_nd_c_info():
        """Po kliknięciu 'Pokaż' liczymy Nd i C w wybranym zakresie i potem odświeżamy tabelę."""
        sm = start_month_var.get()
        sy = start_year_var.get()
        em = end_month_var.get()
        ey = end_year_var.get()

        for u in users:
            nd_sum, c_sum = calculate_nd_c_for_user_in_period(
                group_name, u, sm, sy, em, ey)
            user_nd_c[u] = (nd_sum, c_sum)

        update_table()  # odśwież układ tabeli, wstawi obliczone ND/C

    tk.Button(range_frame, text="Pokaż Nd./L4", command=update_nd_c_info).pack(
        side=tk.LEFT, padx=5)

    def update_table():
        """Rysujemy tabelę: [Lp] [Nazwisko i imię] [Nd] [C] [Akcja]."""
        for widget in data_frame.winfo_children():
            widget.destroy()

        # Nagłówek tabeli
        tk.Label(data_frame, text="Lp", width=3, borderwidth=1, relief="solid") \
          .grid(row=0, column=0, sticky="nsew")
        tk.Label(data_frame, text="Nazwisko i imię", width=25, borderwidth=1, relief="solid") \
          .grid(row=0, column=1, sticky="nsew")
        tk.Label(data_frame, text="Ilość niedz.", width=10, borderwidth=1, relief="solid") \
          .grid(row=0, column=2, sticky="nsew")
        tk.Label(data_frame, text="Ilość L4", width=8, borderwidth=1, relief="solid") \
          .grid(row=0, column=3, sticky="nsew")
        tk.Label(data_frame, text="Akcja", width=25, borderwidth=1, relief="solid") \
          .grid(row=0, column=4, sticky="nsew")
        

        # Wiersze z użytkownikami
        for index, user in enumerate(users, start=1):
            nd_val = 0
            c_val = 0
            if user in user_nd_c:
                nd_val, c_val = user_nd_c[user]

            tk.Label(data_frame, text=index, width=3, borderwidth=1, relief="solid", anchor="center") \
              .grid(row=index, column=0, sticky="nsew")
            tk.Label(data_frame, text=user, width=25, borderwidth=1, relief="solid", anchor="w") \
              .grid(row=index, column=1, sticky="nsew")
            tk.Label(data_frame, text=str(nd_val), width=10, borderwidth=1, relief="solid", anchor="center") \
              .grid(row=index, column=2, sticky="nsew")
            tk.Label(data_frame, text=str(c_val), width=8, borderwidth=1, relief="solid", anchor="center") \
              .grid(row=index, column=3, sticky="nsew")


            actions_frame = tk.Frame(data_frame, borderwidth=0)
            actions_frame.grid(row=index, column=4, sticky="nsew")

            tk.Button(actions_frame, text="↑", width=2,
                      command=lambda i=index-1: move_up(i))\
                .pack(side=tk.LEFT, padx=2)
            tk.Button(actions_frame, text="↓", width=2,
                      command=lambda i=index-1: move_down(i))\
                .pack(side=tk.LEFT, padx=2)
            tk.Button(actions_frame, text="Edytuj",
                      command=lambda i=index-1: edit_user(i))\
                .pack(side=tk.LEFT, padx=2)
            tk.Button(actions_frame, text="Usuń",
                      command=lambda i=index-1: remove_user(i))\
                .pack(side=tk.LEFT, padx=2)
            tk.Button(actions_frame, text="Przenieś",
                      command=lambda i=index-1: move_user(i))\
                .pack(side=tk.LEFT, padx=2)

    def add_user():
        name = entry.get()
        if name.strip():
            users.append(name.strip())
            entry.delete(0, tk.END)
            update_table()
            save_users_to_file(users)

    def remove_user(idx):
        users.pop(idx)
        update_table()
        save_users_to_file(users)

    def move_up(idx):
        if idx > 0:
            users[idx], users[idx-1] = users[idx-1], users[idx]
            update_table()
            save_users_to_file(users)

    def move_down(idx):
        if idx < len(users)-1:
            users[idx], users[idx+1] = users[idx+1], users[idx]
            update_table()
            save_users_to_file(users)

    def edit_user(idx):
        def save_edit():
            new_name = edit_entry.get()
            if new_name.strip():
                users[idx] = new_name.strip()
                update_table()
                save_users_to_file(users)
                safe_destroy(edit_popup)

        edit_popup = tk.Toplevel(new_window)
        edit_popup.title("Edytuj użytkownika")
        tk.Label(edit_popup, text="Nowa nazwa:").pack(pady=10)
        edit_entry = tk.Entry(edit_popup, width=30)
        edit_entry.insert(0, users[idx])
        edit_entry.pack(pady=5)
        tk.Button(edit_popup, text="Zapisz", command=save_edit).pack(pady=10)

    def move_user(idx):
        user_to_move = users[idx]
        move_window = tk.Toplevel(new_window)
        move_window.title("Przenieś użytkownika")
        tk.Label(move_window, text=f"Przenieś {user_to_move} do:").pack(pady=5)

        target_groups = [g["name"].strip()
                         for g in groups if g["name"].strip() != group_name.strip()]
        if not target_groups:
            messagebox.showerror(
                "Błąd", "Brak innych grup, do których można przenieść użytkownika.")
            move_window.destroy()
            return

        target_group_var = tk.StringVar(value=target_groups[0])
        group_menu = ttk.Combobox(
            move_window, values=target_groups, textvariable=target_group_var, state="readonly")
        group_menu.pack(pady=5)

        def confirm_move():
            target_group_name = target_group_var.get().strip()
            # 1) Załaduj plik docelowej grupy (users.json) i dodaj usera
            target_file = f"{target_group_name}_users.json"
            target_users = load_users_from_file_local(target_file)
            if user_to_move not in target_users:
                target_users.append(user_to_move)
            with open(target_file, "w", encoding="utf-8") as file:
                json.dump(target_users, file, ensure_ascii=False, indent=4)

            # 2) Przenieś dane z plików <grupa_stara>_*.json do <grupa_nowa>_*.json
            pattern_old = f"{group_name.strip()}_*.json"
            for old_json in glob.glob(pattern_old):
                # Odczyt
                try:
                    with open(old_json, "r", encoding="utf-8") as f:
                        old_data = json.load(f)
                        if not isinstance(old_data, dict):
                            continue
                except:
                    continue

                old_month = old_data.get("month")
                old_year = old_data.get("year")
                if not old_month or not old_year:
                    continue
                data_section = old_data.get("data", {})

                # Sprawdź, czy user jest w starym pliku
                if user_to_move in data_section:
                    # Zapisz do nowego pliku
                    new_json_name = f"{target_group_name}_{
                        old_month}_{old_year}.json"
                    # Wczytaj/zaktualizuj docelowy plik
                    new_data = {}
                    if os.path.exists(new_json_name):
                        try:
                            with open(new_json_name, "r", encoding="utf-8") as nf:
                                new_data = json.load(nf)
                                if not isinstance(new_data, dict):
                                    new_data = {}
                        except:
                            new_data = {}
                    # Upewniamy się, że ma klucze: "group", "month", "year", "data"
                    if "group" not in new_data:
                        new_data["group"] = target_group_name
                    if "month" not in new_data:
                        new_data["month"] = old_month
                    if "year" not in new_data:
                        new_data["year"] = old_year
                    if "data" not in new_data:
                        new_data["data"] = {}

                    # Dodajemy usera do new_data
                    new_data["data"][user_to_move] = data_section[user_to_move]

                    # Usuwamy usera ze starego
                    del data_section[user_to_move]

                    # Zapisz stary plik (już bez usera)
                    with open(old_json, "w", encoding="utf-8") as f:
                        old_data["data"] = data_section
                        json.dump(old_data, f, ensure_ascii=False, indent=4)

                    # Zapisz docelowy plik
                    with open(new_json_name, "w", encoding="utf-8") as nf:
                        json.dump(new_data, nf, ensure_ascii=False, indent=4)

            # 3) Usuń użytkownika z bieżącej grupy i zapisz
            users.pop(idx)
            update_table()
            save_users_to_file(users)

            messagebox.showinfo("Sukces", f"Użytkownik {
                                user_to_move} został przeniesiony do grupy {target_group_name}.")
            move_window.destroy()

        tk.Button(move_window, text="Przenieś",
                  command=confirm_move).pack(pady=5)

    # Wywołanie początkowego zbudowania tabeli
    update_table()

    # Funkcja zmiany nazwy grupy
    def change_group_name():
        name_window = tk.Toplevel(new_window)
        name_window.title("Zmień nazwę grupy")
        tk.Label(name_window, text="Nowa nazwa grupy:").pack(pady=5)
        new_name_entry = tk.Entry(name_window)
        new_name_entry.pack(pady=5)

        def save_new_name():
            new_name = new_name_entry.get().strip()
            if not new_name:
                messagebox.showerror("Błąd", "Nazwa nie może być pusta!")
                return
            group = get_group_by_name(group_name)
            if group:
                group["name"] = f"{new_name[:25]:<25}"
                new_window.title(f"Grupa: {group['name'].strip()}")
                messagebox.showinfo("Sukces", "Nazwa grupy została zmieniona!")
                save_groups()
                name_window.destroy()
            else:
                messagebox.showerror("Błąd", "Nie znaleziono grupy.")

        tk.Button(name_window, text="Zapisz",
                  command=save_new_name).pack(pady=5)

    # Funkcja usuwania grupy
    def delete_group_logged():
        if messagebox.askyesno("Potwierdzenie", "Czy na pewno chcesz usunąć tę grupę?"):
            group = get_group_by_name(group_name)
            if group:
                safe_destroy(group["frame"])
                groups.remove(group)
                save_groups()
                messagebox.showinfo("Sukces", "Grupa została usunięta!")
                new_window.destroy()
                if root.winfo_exists():
                    root.deiconify()
            else:
                messagebox.showerror("Błąd", "Nie znaleziono grupy.")


def change_group_credentials(group_name):
    group_name = group_name.strip()
    group = get_group_by_name(group_name)
    if not group:
        messagebox.showerror("Błąd", f"Nie znaleziono grupy '{group_name}'.")
        return

    cred_window = tk.Toplevel(root)
    cred_window.title("Zmień dane logowania")
    cred_window.geometry("300x200")

    tk.Label(cred_window, text="Nowy login:").pack(pady=5)
    login_entry = tk.Entry(cred_window)
    login_entry.insert(0, group["login"])
    login_entry.pack(pady=5)

    tk.Label(cred_window, text="Nowe hasło:").pack(pady=5)
    password_entry = tk.Entry(cred_window, show="*")
    password_entry.insert(0, group["password"])
    password_entry.pack(pady=5)

    def save_credentials():
        new_login = login_entry.get().strip()
        new_pass = password_entry.get().strip()
        if not new_login or not new_pass:
            messagebox.showerror("Błąd", "Login i hasło nie mogą być puste!")
            return
        group["login"] = new_login
        group["password"] = new_pass
        save_groups()
        messagebox.showinfo("Sukces", "Dane logowania zostały zmienione!")
        cred_window.destroy()

    tk.Button(cred_window, text="Zapisz",
              command=save_credentials).pack(pady=10)

# ===================== OKNO TWORZENIA KONTA I LOGOWANIA =====================


def open_account_creation_window(group_name):
    """Okno tworzenia konta dla nowej grupy (login i hasło)."""
    ac_window = tk.Toplevel(root)
    ac_window.title(f"Utwórz konto dla grupy: {group_name.strip()}")
    ac_window.geometry("300x200")

    tk.Label(ac_window, text="Login:").pack(pady=5)
    login_entry = tk.Entry(ac_window)
    login_entry.pack(pady=5)

    tk.Label(ac_window, text="Hasło:").pack(pady=5)
    password_entry = tk.Entry(ac_window, show="*")
    password_entry.pack(pady=5)

    def create_account():
        login = login_entry.get().strip()
        password = password_entry.get().strip()
        if not login or not password:
            messagebox.showerror("Błąd", "Login i hasło nie mogą być puste!")
            return
        add_group_from_data(group_name, login, password)
        save_groups()
        safe_destroy(ac_window)

    tk.Button(ac_window, text="Utwórz konto",
              command=create_account).pack(pady=10)


def open_login_window(grp):
    """Okno logowania do wybranej grupy."""
    login_window = tk.Toplevel(root)
    login_window.title(f"Zaloguj w {grp['name'].strip()}")
    login_window.geometry("300x200")

    tk.Label(login_window, text="Login:").pack(pady=5)
    login_entry = tk.Entry(login_window)
    login_entry.pack(pady=5)

    tk.Label(login_window, text="Hasło:").pack(pady=5)
    password_entry = tk.Entry(login_window, show="*")
    password_entry.pack(pady=5)

    def attempt_login():
        login = login_entry.get().strip()
        password = password_entry.get().strip()
        # Jeśli dane administratora:
        if login == ADMIN_LOGIN and password == ADMIN_PASSWORD:
            safe_destroy(login_window)
            root.withdraw()
            open_new_window(grp["name"].strip())
        elif login == grp["login"] and password == grp["password"]:
            safe_destroy(login_window)
            root.withdraw()
            open_new_window(grp["name"].strip())
        else:
            messagebox.showerror("Błąd", "Niepoprawny login lub hasło!")

    tk.Button(login_window, text="Zaloguj",
              command=attempt_login).pack(pady=10)

# ===================== OKNO GŁÓWNE – ZARZĄDZANIE GRUPAMI =====================


def add_group_from_data(group_name, login, password):
    formatted_group_name = f"{group_name[:25]:<25}"
    group_frame = tk.Frame(root, width=400, height=30)
    group_frame.place(x=10, y=50 + len(groups) * 40)

    group_dict = {
        "name": formatted_group_name,
        "login": login,
        "password": password,
        "frame": group_frame
    }
    groups.append(group_dict)

    button = tk.Button(
        group_frame,
        text=formatted_group_name,
        width=25,
        anchor="w",
        command=lambda: open_login_window(
            get_group_by_name(formatted_group_name))
    )
    button.pack(side=tk.LEFT)


def add_group():
    entry = tk.Entry(root)
    entry.place(x=10, y=50 + len(groups) * 40)

    def on_add():
        group_name = entry.get()
        if group_name:
            safe_destroy(entry)
            safe_destroy(add_button)
            open_account_creation_window(group_name)
        else:
            messagebox.showerror("Błąd", "Nazwa grupy nie może być pusta!")

    add_button = tk.Button(root, text="Dodaj", command=on_add)
    add_button.place(x=150, y=50 + len(groups) * 40)


# ===================== GŁÓWNE OKNO APLIKACJI =====================
root = tk.Tk()
root.title("HRoMonitor v1.0 by Hubert Dziczek")
root.geometry("400x600")

add_group_button = tk.Button(root, text="Dodaj nowy dział", command=add_group)
add_group_button.place(x=10, y=10)

# Wczytujemy zapisane grupy (jeśli plik istnieje)
saved_groups = load_groups()
for grp in saved_groups:
    if isinstance(grp, dict):
        add_group_from_data(grp["name"], grp["login"], grp["password"])
    else:
        # Stary format
        add_group_from_data(grp, "admin", "admin")

root.mainloop()
