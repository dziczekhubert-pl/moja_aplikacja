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
    # API do schematów:
    path("api/", include("schedule.urls")),   # lub path("", include("schedule.urls")) jeśli ścieżki zaczynają się od 'api/templates/...'
    path("logout/<str:group>/", logout_view, name="logout"),
]
