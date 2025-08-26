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
    notify_email,   # <-- nowy widok do wysyłki e-maili
)

urlpatterns = [
    path("", start, name="start"),
    path("login/<str:group>/", login_view, name="login"),
    path("panel/<str:group>/", panel, name="panel"),
    path("delete/<str:group>/", delete_group, name="delete_group"),
    path("ping/", ping, name="ping"),
    path("tabela/<str:group>/", tabela, name="tabela"),
    path("edycja/<str:group>/", edit_table, name="edit_table"),
    path("edycja/<str:group>/autosave/", autosave_cell, name="autosave_cell"),
    path("grafik/<str:group>/", grafik_view, name="grafik"),
    path("grafik/<str:group>/notify-email/", notify_email, name="notify_email"),  # <-- TA LINIA
    path("api/", include("schedule.urls")),
    path("logout/<str:group>/", logout_view, name="logout"),

    # NOWE: endpoint do powiadomień e-mail
    path("grafik/<str:group>/notify-email/", notify_email, name="notify_email"),

    # API do schematów (app: schedule)
    path("api/", include("schedule.urls")),

    path("logout/<str:group>/", logout_view, name="logout"),
]
