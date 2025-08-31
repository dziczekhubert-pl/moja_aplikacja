from django.urls import path, include
from .views import (
    start,
    login_view,
    panel,
    delete_group,
    ping,
    tabela,
    edit_table,
    autosave_cell,
    logout_view,
    grafik_view,
    notify_email,
    employee_profile,
    export_profiles_csv,   # <- NOWE
    import_profiles_csv,   # <- NOWE
)

urlpatterns = [
    # start / logowanie / wylogowanie
    path("", start, name="start"),
    path("login/<str:group>/", login_view, name="login"),
    path("logout/<str:group>/", logout_view, name="logout"),

    # panel + CSV
    path("panel/<str:group>/", panel, name="panel"),
    path("panel/<str:group>/export-csv/", export_profiles_csv, name="export_profiles_csv"),
    path("panel/<str:group>/import-csv/", import_profiles_csv, name="import_profiles_csv"),

    # profil pracownika
    path("profil/<str:group>/<path:emp_name>/", employee_profile, name="employee_profile"),

    # grafik + powiadomienia e-mail
    path("grafik/<str:group>/", grafik_view, name="grafik"),
    path("grafik/<str:group>/notify-email/", notify_email, name="notify_email"),

    # edycja tabeli + autosave
    path("edycja/<str:group>/", edit_table, name="edit_table"),
    path("edycja/<str:group>/autosave/", autosave_cell, name="autosave_cell"),

    # inne
    path("tabela/<str:group>/", tabela, name="tabela"),
    path("delete/<str:group>/", delete_group, name="delete_group"),
    path("api/", include("schedule.urls")),
    path("ping/", ping, name="ping"),
]
