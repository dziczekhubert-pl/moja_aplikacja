"""
Django settings for moja_aplikacja project.
Dostosowane pod deploy na Render.
"""

from pathlib import Path
import os
import dj_database_url

# === Ścieżki ===
BASE_DIR = Path(__file__).resolve().parent.parent

# === Bezpieczeństwo / tryb ===
# Na produkcji ustawimy SECRET_KEY w zmiennych środowiskowych (Render → Environment)
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
DEBUG = os.environ.get("DEBUG", "False").lower() == "true"

# Render podaje nazwę hosta w RENDER_EXTERNAL_HOSTNAME
ALLOWED_HOSTS = [os.environ.get("RENDER_EXTERNAL_HOSTNAME", ""), "localhost", "127.0.0.1"]

# CSRF na produkcji (gdy Render ustawi hosta)
render_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if render_host:
    CSRF_TRUSTED_ORIGINS = [f"https://{render_host}"]

# === Aplikacje ===
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'pierwsza_app',
]

# === Middleware ===
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # serwowanie statyków w produkcji
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'moja_aplikacja.urls'

# === Szablony ===
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],  # jeśli masz globalny katalog szablonów, dodaj ścieżkę
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'moja_aplikacja.wsgi.application'

# === Baza danych ===
# Jeśli jest DATABASE_URL (Render/Postgres) -> użyj go z SSL,
# jeśli nie ma -> lokalnie użyj sqlite bez SSL (żeby nie było błędu sslmode przy sqlite).
DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.config(
            conn_max_age=600,
            ssl_require=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# === Walidacja haseł ===
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# === Internationalization ===
LANGUAGE_CODE = 'en-us'     # Możesz zmienić na 'pl'
TIME_ZONE = 'UTC'           # Możesz zmienić na 'Europe/Warsaw'
USE_I18N = True
USE_TZ = True

# === Statyczne pliki (CSS/JS/obrazki) ===
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# === Klucz domyślny ===
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
