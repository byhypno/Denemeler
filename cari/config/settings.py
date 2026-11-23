"""Cari program ayarları — tek bilgisayarda, yerelde çalışacak şekilde."""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Veritabanı, ekler ve gizli anahtar BURADA tutulur. Bu klasör depoya girmez (.gitignore).
VERI_DIZINI = Path(os.environ.get("CARI_VERI_DIZINI", BASE_DIR / "veri"))
VERI_DIZINI.mkdir(parents=True, exist_ok=True)


def _gizli_anahtar() -> str:
    if os.environ.get("CARI_SECRET_KEY"):
        return os.environ["CARI_SECRET_KEY"]
    dosya = VERI_DIZINI / "secret.key"
    if not dosya.exists():
        dosya.write_text(secrets.token_urlsafe(50))
        try:
            dosya.chmod(0o600)
        except OSError:
            pass
    return dosya.read_text().strip()


# Ek dosyalar (fiş görseli, ekstre PDF'i vb.): içerik hash'iyle adlandırılır, yalnızca giriş yapmış
# kullanıcıya özel bir görünümle sunulur (statik/medya adresi YOKTUR). Yedek alırken bu klasör de alınmalıdır.
EK_DIZINI = Path(os.environ.get("CARI_EK_DIZINI", VERI_DIZINI / "ekler"))
EK_MAX_BAYT = 20 * 1024 * 1024      # dosya başına
EK_MAX_ADET = 20                    # tek yüklemede

# Yedek hedefleri (birden fazla olabilir; Windows'ta ';' ile ayrılır): ör. CARI_YEDEK_DIZINLERI=D:\\Yedek;E:\\Yedek
# Yedekler AYNI DİSKTE tutulursa disk bozulunca hepsi gider; mümkünse ayrı disk/USB kullanın.
YEDEK_DIZINLERI = [Path(p) for p in os.environ.get("CARI_YEDEK_DIZINLERI", "").split(os.pathsep) if p.strip()]
YEDEK_UYARI_GUN = 2                 # bu kadar günden eski son yedek için uyarı gösterilir
YEDEK_GUNLUK_SAKLA = 30             # son N gün: her yedek saklanır
YEDEK_AYLIK_SAKLA = 12              # daha eskiler: ay başına en son yedek, son N ay

SECRET_KEY = _gizli_anahtar()
DEBUG = os.environ.get("CARI_DEBUG", "0") == "1"
# Sadece bu bilgisayardan erişim. Ağdan erişim ileride bilinçli olarak açılacak.
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "defter",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "defter.gunluk.KullaniciIzlemeMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "defter.context.genel",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": VERI_DIZINI / "cari.sqlite3",
        "OPTIONS": {
            "timeout": 20,
            "transaction_mode": "IMMEDIATE",
            # WAL: okuma/yazma çakışmasını azaltır; yabancı anahtar kontrolü açık.
            "init_command": (
                "PRAGMA journal_mode=WAL;"
                "PRAGMA synchronous=NORMAL;"
                "PRAGMA foreign_keys=ON;"
            ),
        },
    }
}

import sys  # noqa: E402

if "test" in sys.argv:
    # Yalnızca testler: parola özetleme yavaş olduğundan hızlı (güvensiz) bir özetleyici kullanılır.
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

FORMAT_MODULE_PATH = ["config.formats"]
LANGUAGE_CODE = "tr"
TIME_ZONE = "Europe/Istanbul"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
WHITENOISE_USE_FINDERS = True  # collectstatic olmadan da admin dosyalarını sunar
WHITENOISE_AUTOREFRESH = DEBUG  # geliştirirken dosya değişince yeniden okur

LOGIN_URL = "/giris/"
LOGIN_REDIRECT_URL = "/"
SESSION_COOKIE_AGE = 60 * 60 * 8  # 8 saat
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

DATA_UPLOAD_MAX_NUMBER_FILES = 25
FILE_UPLOAD_PERMISSIONS = 0o600
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Sunucu kaydı: neden durduğunu/hata verdiğini sonradan görebilmek için veri klasöründe dönen (rotating) kayıt dosyası.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"d": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {
        "dosya": {"class": "logging.handlers.RotatingFileHandler", "filename": str(VERI_DIZINI / "sunucu.log"),
                  "maxBytes": 1_000_000, "backupCount": 3, "encoding": "utf-8", "formatter": "d", "delay": True},
    },
    "loggers": {
        "defter.sunucu": {"handlers": ["dosya"], "level": "INFO", "propagate": True},
        "django.request": {"handlers": ["dosya"], "level": "ERROR", "propagate": True},
        "django.server": {"handlers": ["dosya"], "level": "ERROR", "propagate": True},
        "waitress": {"handlers": ["dosya"], "level": "WARNING", "propagate": True},
    },
}

