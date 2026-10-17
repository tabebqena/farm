#!/usr/bin/env sh
# Container entrypoint: apply schema migrations and collect static assets before
# handing control to the main process (gunicorn). Both steps are idempotent and
# can be disabled with DJANGO_RUN_MIGRATIONS=0 / DJANGO_COLLECTSTATIC=0.
set -e

if [ "${DJANGO_RUN_MIGRATIONS:-1}" = "1" ]; then
  echo "Applying database migrations..."
  python manage.py migrate --noinput
fi

if [ "${DJANGO_COLLECTSTATIC:-1}" = "1" ]; then
  echo "Collecting static files..."
  python manage.py collectstatic --noinput
fi

exec "$@"
