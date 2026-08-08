#!/bin/bash
set -e
cd "/home/faizan/projects/Salesforce-Inspector reloaded/backend"
export PATH=/usr/bin:/bin
export PGCONNECT_TIMEOUT=5
export PGPASSWORD=$(sed -n 's/^SFIR_DATABASE_URL=postgresql+asyncpg:\/\/sfir:\([^@]*\)@.*/\1/p' .env | head -1)
psql -w -h localhost -U sfir -d sfir -Atc \
  "SELECT column_name FROM information_schema.columns WHERE table_name='organizations' AND column_name IN ('salesforce_org_id','salesforce_org_name','instance_url','organization_type') ORDER BY column_name;"
psql -w -h localhost -U sfir -d sfir -Atc \
  "SELECT conname FROM pg_constraint WHERE conname='uq_organizations_salesforce_org_id';"
