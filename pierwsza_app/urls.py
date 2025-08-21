from django.urls import path
from .views import (
    start,
    login_view,
    panel,
    delete_group,
    ping,
    tabela,
    edit_table,
    autosave_cell,   # <-- ważne
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
]
