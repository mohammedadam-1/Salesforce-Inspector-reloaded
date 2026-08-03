#!/usr/bin/env bash
# Stage 0B repair runbook — Option D (approved), D2-i variant: NO migration edits.
# Order: preflight (env verification) -> guard (read-only) -> stamp 001 -> verify ->
#        install pg_trgm -> verify -> upgrade head -> verify -> Stage 0 result summary
set -Eeuo pipefail

BACKEND="/home/faizan/projects/Salesforce-Inspector reloaded/backend"
cd "$BACKEND" || { echo "FATAL: cannot cd to $BACKEND"; exit 1; }

ALEMBIC="Agent.env/bin/python -m alembic"
psqlq() { docker exec -i sfir-postgres psql -U sfir -d sfir -tAc "$1"; }

STAGE=PASS

echo "================ PREFLIGHT: ENVIRONMENT VERIFICATION ================"
echo "Python:"
Agent.env/bin/python --version

echo "Python Executable:"
Agent.env/bin/python -c "import sys; print(sys.executable)"

echo "Alembic:"
Agent.env/bin/python -m alembic --version

echo "Database URL:"
PYTHONPATH=src Agent.env/bin/python -c "
from sfir_backend.config.settings import get_settings
from urllib.parse import urlparse
u = urlparse(get_settings().database_url.get_secret_value())
print(f'{u.scheme}://{u.username}:***@{u.hostname}:{u.port}{u.path}')
"
echo "PREFLIGHT OK."

echo "================ STEP 0: PRECONDITION GUARD (read-only) ================"
V=$(psqlq "SELECT version_num FROM alembic_version")
T=$(psqlq "SELECT to_regclass('public.metadata_objects')")
echo "alembic_version.version_num = '$V'"
echo "metadata_objects exists     = '$T'"
if [ "$V" != "002" ]; then
  echo "GUARD FAILED: version_num is '$V', expected '002'. State differs from inspection. ABORT — no changes made."
  exit 1
fi
if [ -n "$T" ]; then
  echo "Already repaired: revision 002 objects present. Nothing to do. Exiting 0."
  exit 0
fi
echo "GUARD OK. Proceeding with repair."

echo "================ STEP 1: STAMP REVISION 001 ================"
$ALEMBIC stamp 001

echo "================ STEP 2: VERIFY REVISION ================"
$ALEMBIC current
$ALEMBIC heads
echo "alembic_version table:"
docker exec -i sfir-postgres psql -U sfir -d sfir -c "SELECT version_num FROM alembic_version"

echo "================ STEP 3: INSTALL pg_trgm ================"
docker exec -i sfir-postgres psql -U sfir -d sfir -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"

echo "================ STEP 4: VERIFY pg_trgm ================"
docker exec -i sfir-postgres psql -U sfir -d sfir -c "SELECT extname, extversion FROM pg_extension WHERE extname='pg_trgm';"

echo "================ STEP 5: RUN alembic upgrade head ================"
if ! $ALEMBIC upgrade head; then
  echo "UPGRADE FAILED — see output above."
  STAGE=FAIL
fi

echo "================ STEP 6: POST-UPGRADE VERIFICATION ================"
$ALEMBIC current
docker exec -i sfir-postgres psql -U sfir -d sfir -c "\dt metadata_*"
docker exec -i sfir-postgres psql -U sfir -d sfir -c "SELECT indexname, tablename FROM pg_indexes WHERE indexname IN ('ix_metadata_validation_rules_formula','ix_search_documents_title_trgm') ORDER BY 1;"

echo "===================================="
echo "Stage 0 Result"
echo ""
echo "Alembic Revision:"
REV=$(Agent.env/bin/python -m alembic current 2>/dev/null | tail -1 || true)
echo "$REV"
echo ""
echo "Metadata Tables:"
MTABLES=$(psqlq "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND (table_name LIKE 'metadata_%' OR table_name='search_documents')")
echo "$MTABLES"
echo ""
echo "pg_trgm:"
TRGM=$(psqlq "SELECT count(*) FROM pg_extension WHERE extname='pg_trgm'")
[ "$TRGM" = "1" ] && echo "present" || echo "ABSENT"
echo ""
if [ "$STAGE" = "FAIL" ] || ! echo "$REV" | grep -q "002 (head)" || [ "$MTABLES" != "16" ] || [ "$TRGM" != "1" ]; then
  echo "FAIL"
else
  echo "PASS"
fi
echo "===================================="
