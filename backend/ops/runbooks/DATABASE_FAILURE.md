# Database Failure Runbook

## Symptoms
- API returns 503 errors
- Health check `/api/v1/health/ready` reports database as unhealthy
- Error logs show `DatabaseError` or `connection refused`
- Increased latency on all database-dependent endpoints

## Severity Levels
| Level | Impact | Response Time |
|-------|--------|---------------|
| SEV1  | Complete outage | < 15 min |
| SEV2  | Degraded performance | < 60 min |
| SEV3  | Minor connection issues | < 4 hours |

## Immediate Actions (SEV1)

1. **Verify the issue:**
   ```bash
   kubectl exec -it deploy/sfir-api -n sfir -- python -c "
   import asyncio, asyncpg
   async def check():
       try:
           conn = await asyncpg.connect('postgresql://sfir:@sfir-postgres:5432/sfir')
           await conn.close()
           print('OK')
       except Exception as e:
           print(f'FAIL: {e}')
   asyncio.run(check())
   "
   ```

2. **Check Postgres pod status:**
   ```bash
   kubectl get pods -n sfir -l app.kubernetes.io/component=database
   kubectl describe pod sfir-postgres-0 -n sfir
   kubectl logs sfir-postgres-0 -n sfir --tail=100
   ```

3. **Restart Postgres (if unresponsive):**
   ```bash
   kubectl delete pod sfir-postgres-0 -n sfir --wait=false
   ```

4. **Check disk space:**
   ```bash
   kubectl exec sfir-postgres-0 -n sfir -- df -h /var/lib/postgresql/data
   ```

## Recovery Procedures

### Connection Pool Exhaustion
```bash
# Increase pool size
kubectl set env deployment/sfir-api -n sfir SFIR_DATABASE_POOL_SIZE=50
kubectl set env deployment/sfir-api -n sfir SFIR_DATABASE_MAX_OVERFLOW=100
```

### Replication Lag (Read Replica)
```bash
# Check lag
kubectl exec sfir-postgres-0 -n sfir -- psql -U sfir -c "
SELECT application_name, state, sync_state,
       pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS lag_bytes
FROM pg_stat_replication;
"
```

### Point-in-Time Recovery
```bash
# Identify target time
# Restore from WAL archive
kubectl exec sfir-postgres-0 -n sfir -- bash -c "
pg_ctl stop -D /var/lib/postgresql/data/pgdata
rm -rf /var/lib/postgresql/data/pgdata
pg_basebackup -h <backup-server> -D /var/lib/postgresql/data/pgdata -P -U replicator
pg_ctl start -D /var/lib/postgresql/data/pgdata
"
```

## Prevention
- Configure PgBouncer for connection pooling
- Set up streaming replicas for read scaling
- Schedule regular `VACUUM ANALYZE` jobs
- Monitor connection count with alerts at 80% of max
- Enable `pg_stat_statements` for query performance tracking
