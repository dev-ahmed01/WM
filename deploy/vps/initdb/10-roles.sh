#!/bin/sh
# Runs once, on first start of an empty data directory. Creates the NON-owner application login the API uses.
# The owner (POSTGRES_USER) runs migrations and backups; the app login is subject to row-level security.
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
CREATE ROLE workmate_scoped_reader NOLOGIN;
CREATE ROLE ${APP_DB_USER} LOGIN PASSWORD '${APP_DB_PASSWORD}'
  NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
SQL
