from pathlib import Path
from urllib.parse import urlparse


def config(default=None, conn_max_age=0):
    url = default or "sqlite:///db.sqlite3"
    parsed = urlparse(url)

    if parsed.scheme == "sqlite":
        path = parsed.path or "/db.sqlite3"
        return {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": Path(path.lstrip("/")),
        }

    engine_map = {
        "postgres": "django.db.backends.postgresql",
        "postgresql": "django.db.backends.postgresql",
        "postgresql_psycopg2": "django.db.backends.postgresql",
        "mysql": "django.db.backends.mysql",
    }

    return {
        "ENGINE": engine_map.get(parsed.scheme, "django.db.backends.sqlite3"),
        "NAME": parsed.path.lstrip("/"),
        "USER": parsed.username or "",
        "PASSWORD": parsed.password or "",
        "HOST": parsed.hostname or "",
        "PORT": parsed.port or "",
        "CONN_MAX_AGE": conn_max_age,
    }
