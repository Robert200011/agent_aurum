#!/bin/sh
set -eu

psql \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --set=ON_ERROR_STOP=1 \
  --set=app_password="$AURUM_APP_DB_PASSWORD" <<-'SQL'
SELECT 'CREATE ROLE aurum_app LOGIN PASSWORD ' || quote_literal(:'app_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aurum_app')
\gexec

GRANT CONNECT ON DATABASE aurum TO aurum_app;
SQL
