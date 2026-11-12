"""Settings for Workbench.

Everything that differs between your Mac and the hosted site comes from
environment variables. Locally you can put them in a `.env` file next to
manage.py (see `.env.example`); on Vercel, set them in Project Settings →
Environment Variables.
"""
import os
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path):
    """Minimal .env loader (KEY=value lines). Real environment variables win."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


# `.env` by default; `ENV_FILE=.env.production python manage.py migrate` targets Supabase.
_load_dotenv(BASE_DIR / os.environ.get("ENV_FILE", ".env"))


def env_bool(name, default):
    return os.environ.get(name, "1" if default else "0").strip().lower() in ("1", "true", "yes", "on")


ON_VERCEL = bool(os.environ.get("VERCEL"))

# Shown in the header and browser tab.
SITE_NAME = os.environ.get("SITE_NAME", "Workbench")

# Shown on the public landing page.
OWNER_NAME = os.environ.get("OWNER_NAME", "Elaiza Remo")
OWNER_URL = os.environ.get("OWNER_URL", "")      # your personal website
REPO_URL = os.environ.get("REPO_URL", "")        # this project's GitHub repo, if public

DEBUG = env_bool("DJANGO_DEBUG", default=not ON_VERCEL)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError("Set DJANGO_SECRET_KEY (any long random string) before running with DEBUG off.")
    SECRET_KEY = "dev-only-insecure-key"

ALLOWED_HOSTS = [h for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h]
CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o]
if ON_VERCEL:
    ALLOWED_HOSTS.append(".vercel.app")
    CSRF_TRUSTED_ORIGINS.append("https://*.vercel.app")
    for var in ("VERCEL_PROJECT_PRODUCTION_URL", "VERCEL_URL"):
        host = os.environ.get(var)
        if host:
            ALLOWED_HOSTS.append(host)
            CSRF_TRUSTED_ORIGINS.append(f"https://{host}")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
    "prep",
    "journal",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Every page needs a login except the ones marked @login_not_required (landing, login, demo, cron).
    "django.contrib.auth.middleware.LoginRequiredMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.site",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# ---------------------------------------------------------------- database
# Locally: SQLite (db.sqlite3) unless DATABASE_URL is set.
# Hosted: DATABASE_URL = Supabase's *transaction pooler* URI (port 6543).

def _database_from_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in ("postgres", "postgresql"):
        raise RuntimeError("DATABASE_URL must be a postgres:// or postgresql:// URL.")
    query = {k: v[-1] for k, v in parse_qs(parsed.query).items()}
    pooled = parsed.port == 6543  # Supabase transaction pooler
    options = {"sslmode": query.get("sslmode", "require")}
    if pooled:
        # The transaction pooler can't keep prepared statements between queries.
        options["prepare_threshold"] = None
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": parsed.path.lstrip("/") or "postgres",
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname,
        "PORT": parsed.port or 5432,
        "OPTIONS": options,
        "CONN_MAX_AGE": 0 if pooled else 60,
        # Server-side cursors don't survive the transaction pooler either.
        "DISABLE_SERVER_SIDE_CURSORS": pooled,
    }


if os.environ.get("DATABASE_URL"):
    DATABASES = {"default": _database_from_url(os.environ["DATABASE_URL"])}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}


# ---------------------------------------------------------------- accounts

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "home"  # back to the public landing page
SESSION_COOKIE_AGE = 60 * 60 * 24 * 30  # stay signed in for 30 days

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

# The public sandbox account behind "Try the demo". Its data is sample data and
# is wiped and re-seeded every night.
DEMO_ENABLED = env_bool("DEMO_ENABLED", default=True)
DEMO_USERNAME = "demo"

# Vercel Cron sends "Authorization: Bearer $CRON_SECRET" to the nightly reset endpoint.
CRON_SECRET = os.environ.get("CRON_SECRET", "")


# ---------------------------------------------------------------- security (hosted)

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SSL_REDIRECT", default=True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"


# ---------------------------------------------------------------- misc

LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/Edmonton"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"  # Vercel runs collectstatic and serves these from its CDN
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Optional AI feedback in practice mode. Leave unset to hide the feature.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")

# Optional: lets commit import read private GitHub repos and raises the rate limit.
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
