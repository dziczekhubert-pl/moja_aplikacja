from django.urls import path
from . import views  # ważne!

urlpatterns = [
    # start / logowanie
    path("", views.start, name="start"),
    path("login/<str:group>/", views.login_view, name="login"),
    path("logout/<str:group>/", views.logout_view, name="logout"),

    # panel
    path("panel/<str:group>/", views.panel, name="panel"),

    # eksport / import PROFILI
    path("panel/<str:group>/export-csv/", views.export_profiles_csv, name="export_profiles_csv"),
    path("panel/<str:group>/import-csv/", views.import_profiles_csv, name="import_profiles_csv"),
    path("export-profiles-stats/<str:group>/", views.export_profiles_with_stats_csv,
         name="export_profiles_with_stats_csv"),

    # eksport / import SIATKI (tokeny 1/2/3/C)
    path("export-month/<str:group>/", views.export_month_tokens_csv, name="export_month_tokens_csv"),
    path("import-month/<str:group>/", views.import_month_tokens_csv, name="import_month_tokens_csv"),

    # autosave komórki (AJAX)  <<< DODANE >>>
    path("autosave/<str:group>/", views.autosave_cell, name="autosave_cell"),

    # grafik (widok dzienny) + notyfikacja e-mail
    path("grafik/<str:group>/", views.grafik_view, name="grafik"),
    path("grafik/<str:group>/notify-email/", views.notify_email, name="notify_email"),

    # edycja siatki
    path("edycja/<str:group>/", views.edit_table, name="edit"),

    # inne
    path("tabela/<str:group>/", views.tabela, name="tabela"),
    path("set-schedule/<str:group>/", views.set_schedule, name="set_schedule"),
    path("employee/<str:group>/<path:emp_name>/", views.employee_profile, name="employee_profile"),
    path("delete-group/<str:group>/", views.delete_group, name="delete_group"),
    path("ping/", views.ping, name="ping"),
]
