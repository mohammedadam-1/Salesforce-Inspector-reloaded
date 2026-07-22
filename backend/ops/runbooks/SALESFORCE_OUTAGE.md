# Salesforce API Outage Runbook

## Symptoms
- Metadata synchronization failures
- Connection test failures
- Error logs showing `SalesforceApiError` or HTTP 5xx from Salesforce
- Failed OAuth token refreshes

## Severity Levels
| Level | Impact | Response Time |
|-------|--------|---------------|
| SEV1  | Complete sync failure for all orgs | < 30 min |
| SEV2  | Partial sync failure | < 2 hours |

## Immediate Actions

1. **Verify Salesforce status:**
   ```bash
   # Check Salesforce Trust
   curl -s https://api.status.salesforce.com/v1/instances
   
   # Verify rate limit status
   kubectl logs -n sfir -l app.kubernetes.io/component=worker --tail=50 | grep -i "rate_limit"
   ```

2. **Pause sync jobs:**
   ```bash
   kubectl set env deployment/sfir-celery-worker -n sfir SFIR_SALESFORCE_SYNC_PAUSED=true
   ```

3. **Check retry queues:**
   ```bash
   kubectl exec deploy/sfir-api -n sfir -- python -c "
   from redis import Redis
   r = Redis.from_url('redis://sfir-redis:6379/1')
   print(f'Retry queue size: {r.llen(\"sync_retry\")}')
   "
   ```

## Recovery

### When Salesforce recovers:
```bash
# Resume sync
kubectl set env deployment/sfir-celery-worker -n sfir SFIR_SALESFORCE_SYNC_PAUSED=false

# Process retry queue
kubectl exec deploy/sfir-api -n sfir -- python -c "
from redis import Redis
r = Redis.from_url('redis://sfir-redis:6379/1')
# Move retries back to main queue
while r.rpoplpush('sync_retry', 'sync_queue'):
    pass
"
```

### Rate Limit Recovery
- Salesforce uses a sliding window rate limit
- Automatic retry with exponential backoff is built in
- Monitor `SfApiRateLimitExceeded` metric
- If persistent, reduce sync concurrency

## Prevention
- Implement per-org sync scheduling to avoid thundering herd
- Cache Salesforce API responses aggressively
- Maintain last-known-good metadata versions for offline operation
- Monitor Salesforce Trust status feed
