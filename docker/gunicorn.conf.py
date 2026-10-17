"""Gunicorn configuration for the farm project.

Override any value with the matching environment variable, e.g.
``GUNICORN_WORKERS=5``. See https://docs.gunicorn.org/en/stable/settings.html.
"""

import os

bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:8000")
# Threaded workers; keep the worker count modest since SQLite serialises
# writers. Raise GUNICORN_WORKERS for a PostgreSQL deployment.
worker_class = os.environ.get("GUNICORN_WORKER_CLASS", "gthread")
workers = int(os.environ.get("GUNICORN_WORKERS", "3"))
threads = int(os.environ.get("GUNICORN_THREADS", "2"))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "60"))
graceful_timeout = int(os.environ.get("GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.environ.get("GUNICORN_KEEPALIVE", "5"))

accesslog = os.environ.get("GUNICORN_ACCESS_LOG", "-")
errorlog = os.environ.get("GUNICORN_ERROR_LOG", "-")
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")

# Only trust forwarded headers from the local reverse proxy by default.
forwarded_allow_ips = os.environ.get("GUNICORN_FORWARDED_ALLOW_IPS", "127.0.0.1")
