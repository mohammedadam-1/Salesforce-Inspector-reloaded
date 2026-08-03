#!/usr/bin/env bash
P() { docker exec -i sfir-postgres psql -U sfir -d sfir -X -P pager=off "$@"; }

echo "=== 1. pg_class: any relation named ix_metadata_objects_api_name (ALL schemas) ==="
P -c "SELECT c.oid, c.relname, n.nspname AS schema, c.relkind, c.relpersistence, c.relispartition FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relname='ix_metadata_objects_api_name' ORDER BY n.nspname;"

echo "=== 2. pg_class: everything LIKE 'ix_%' or 'metadata%' in non-system schemas ==="
P -c "SELECT c.relname, n.nspname AS schema, c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema','pg_toast') AND (c.relname LIKE 'ix_%' OR c.relname LIKE 'metadata%') ORDER BY n.nspname, c.relname;"

echo "=== 3. all namespaces ==="
P -c "SELECT nspname FROM pg_namespace ORDER BY 1;"

echo "=== 4. pg_indexes view (indexes only) ==="
P -c "SELECT schemaname, indexname, tablename FROM pg_indexes WHERE indexname='ix_metadata_objects_api_name';"

echo "=== 5. pg_tables view (tables only) ==="
P -c "SELECT schemaname, tablename FROM pg_tables WHERE tablename='ix_metadata_objects_api_name';"

echo "=== 6. pg_sequences view (sequences only) ==="
P -c "SELECT schemaname, sequencename FROM pg_sequences WHERE sequencename='ix_metadata_objects_api_name';"

echo "=== 7. pg_constraint ==="
P -c "SELECT conname, conrelid::regclass, contype FROM pg_constraint WHERE conname='ix_metadata_objects_api_name';"

echo "=== 8. pg_type ==="
P -c "SELECT typname, typtype FROM pg_type WHERE typname='ix_metadata_objects_api_name';"

echo "=== 9. pg_trigger ==="
P -c "SELECT tgname, tgrelid::regclass FROM pg_trigger WHERE tgname='ix_metadata_objects_api_name';"

echo "=== 10. pg_depend: what depends ON this object ==="
P -c "SELECT d.objid, d.classid::regclass, d.deptype FROM pg_depend d WHERE d.objid IN (SELECT oid FROM pg_class WHERE relname='ix_metadata_objects_api_name');"

echo "=== 11. pg_depend: what this object depends ON ==="
P -c "SELECT d.refobjid, d.refclassid::regclass, d.deptype, ref.relname AS ref_name, ref.relkind AS ref_kind FROM pg_depend d JOIN pg_class ref ON ref.oid=d.refobjid WHERE d.objid IN (SELECT oid FROM pg_class WHERE relname='ix_metadata_objects_api_name');"

echo "=== 12. metadata_objects in pg_class ==="
P -c "SELECT c.oid, c.relname, n.nspname, c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relname='metadata_objects';"

echo "=== 13. ALL relations in public (every relkind) ==="
P -c "SELECT c.relname, c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' ORDER BY c.relkind, c.relname;"

echo "=== 14. psql \d+ on the object ==="
P -c "\d+ ix_metadata_objects_api_name"

echo "=== 15. pg_stat_activity (concurrent sessions on sfir) ==="
P -c "SELECT pid, usename, state, wait_event_type, wait_event, left(query,120) AS query FROM pg_stat_activity WHERE datname='sfir';"

echo "=== 16. databases in cluster ==="
P -c "SELECT datname FROM pg_database ORDER BY 1;"

echo "=== 17. search_path ==="
P -c "SHOW search_path;"
