#!/bin/sh
set -e

python manage.py migrate --noinput

if [ "${DJANGO_COLLECTSTATIC:-1}" = "1" ]; then
    python manage.py collectstatic --noinput
fi

if [ "$#" -gt 0 ]; then
    exec "$@"
fi

exec python manage.py runserver 0.0.0.0:8000
