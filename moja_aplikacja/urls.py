from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("", include("pierwsza_app.urls")),  # <-- to załatwia / -> start
    path("admin/", admin.site.urls),
]

# Obsługa PDF-ów i innych plików generowanych dynamicznie
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
