from django.urls import path
from . import views

urlpatterns = [
    path("templates/<str:group>/", views.templates_list_create, name="templates_list_create"),
    path("templates/<str:group>/<str:name>/", views.templates_retrieve_update_delete, name="templates_rud"),
]
