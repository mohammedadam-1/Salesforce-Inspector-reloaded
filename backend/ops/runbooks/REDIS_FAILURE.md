# Redis Failure Runbook

## Symptoms
- Cache-dependent features return degraded results
- Rate limiting disabled (falls back to in-memory)
- Celery task queue backlog grows
- Session management degraded

## Severity Levels
| Level | Impact | Response Time |
|-------|--------|---------------|
| SEV1  | Cache completely unavailable | < 15 min |
| SEV2  | Performance degradation | < 30 min |

## Immediate Actions

1. **Verify Redis availability:**
   ```bash
   kubectl exec -it deploy/sfir-api -n sfir -- redis-cli -h sfir-redis ping
   ```

2. **Check Redis pod:**
   ```bash
   kubectl get pods -n sfir -l app.kubernetes.io/component=cache
   kubectl logs sfir-redis-0 -n sfir --tail=50
   ```

3. **Check memory usage:**
   ```bash
   kubectl exec sfir-redis-0 -n sfir -- redis-cli INFO memory | grep used_memory_human
   kubectl exec sfir-redis-0 -n sfir -- redis-cli INFO stats | grep evicted_keys
   ```

4. **Restart Redis (if unresponsive):**
   ```bash
   kubectl delete pod sfir-redis-0 -n sfir --wait=false
   ```

## Recovery

### Memory Pressure
```bash
# Evict non-essential keys
kubectl exec sfir-redis-0 -n sfir -- redis-cli MEMORY PURGE

# Temporarily reduce TTL
kubectl exec sfir-redis-0 -n sfir -- redis-cli CONFIG SET maxmemory 3gb
```

### Data Loss / Corruption
```bash
# Force AOF rewrite
kubectl exec sfir-redis-0 -n sfir -- redis-cli BGREWRITEAOF

# Check AOF
kubectl exec sfir-redis-0 -n sfir -- redis-cli --vaof
```

### Failover to Replica (if configured)
```bash
# Promote replica
kubectl exec sfir-redis-replica-0 -n sfir -- redis-cli SLAVEOF NO ONE
```

## Prevention
- Set `maxmemory-policy allkeys-lru` for automatic eviction
- Configure `maxmemory` to 80% of available instance memory
- Enable AOF persistence with `appendonly yes`
- Monitor `evicted_keys` metric with alert threshold
- Schedule periodic `MEMORY DEFRAG` during low traffic
