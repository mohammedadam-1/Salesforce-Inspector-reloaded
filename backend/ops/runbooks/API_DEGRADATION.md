# API Degradation Runbook

## Symptoms
- Increased p95/p99 latency
- Error rate > 1%
- Timeouts on API endpoints
- Health check failures

## Severity Levels
| Level | Impact | Response Time |
|-------|--------|---------------|
| SEV1  | > 5% error rate, complete outage | < 15 min |
| SEV2  | > 1% error rate, latency 2x baseline | < 60 min |
| SEV3  | Minor degradation | < 4 hours |

## Diagnose

1. **Check pod health:**
   ```bash
   kubectl get pods -n sfir -l app.kubernetes.io/component=api
   kubectl top pods -n sfir -l app.kubernetes.io/component=api
   ```

2. **Check HPA status:**
   ```bash
   kubectl describe hpa sfir-api-hpa -n sfir
   ```

3. **Check recent errors:**
   ```bash
   kubectl logs -n sfir -l app.kubernetes.io/component=api --tail=100 --prefix
   ```

4. **Check slow queries:**
   ```bash
   # Postgres
   kubectl exec sfir-postgres-0 -n sfir -- psql -U sfir -c "
   SELECT query, calls, total_exec_time, mean_exec_time
   FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;
   "
   ```

## Scaling Actions

### Horizontal Scale
```bash
# Manual scale (if HPA not responding)
kubectl scale deployment/sfir-api -n sfir --replicas=10
```

### Resource Limit Increase
```bash
kubectl set resources deployment/sfir-api -n sfir \
  --limits=cpu=4,memory=4Gi \
  --requests=cpu=1,memory=1Gi
```

### Database Tuning
```bash
# Increase connection pool
kubectl set env deployment/sfir-api -n sfir SFIR_DATABASE_POOL_SIZE=50
```

## Rollback

### Rollback Deployment
```bash
kubectl rollout undo deployment/sfir-api -n sfir
kubectl rollout status deployment/sfir-api -n sfir --timeout=5m
```

### Rollback to Specific Revision
```bash
kubectl rollout undo deployment/sfir-api -n sfir --to-revision=3
kubectl rollout status deployment/sfir-api -n sfir --timeout=5m
```
