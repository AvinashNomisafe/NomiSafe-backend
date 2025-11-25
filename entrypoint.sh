#!/bin/sh
set -e

# Default workers
: "${GUNICORN_WORKERS:=3}"

if [ -n "${POSTGRES_DB}" ]; then
  echo "Waiting for PostgreSQL..."
  python - <<'PYCODE'
import os, time, psycopg2
host = os.environ.get('POSTGRES_HOST','db')
port = os.environ.get('POSTGRES_PORT','5432')
user = os.environ['POSTGRES_USER']
password = os.environ['POSTGRES_PASSWORD']
db = os.environ['POSTGRES_DB']
for i in range(30):
    try:
        psycopg2.connect(dbname=db, user=user, password=password, host=host, port=port).close()
        print('Database ready')
        break
    except Exception as e:
        print(f'Attempt {i+1}: DB not ready yet: {e}')
        time.sleep(2)
else:
    raise SystemExit('Database not ready after retries')
PYCODE
fi

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec gunicorn nomisafe_backend.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "$GUNICORN_WORKERS" \
  --access-logfile - \
  --error-logfile -
