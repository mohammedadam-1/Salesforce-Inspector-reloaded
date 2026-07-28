# SFIR — Service Level Objectives & SLIs

## Service Level Indicators (SLIs)

| SLI | Definition | Measurement |
|-----|------------|-------------|
| API Availability | % of successful requests (HTTP 2xx/4xx) | Prometheus: `rate(http_requests_total{status=~"2..|4.."}[5m])` |
| API Latency (p95) | 95th percentile request duration | Prometheus: `histogram_quantile(0.95, http_request_duration_seconds)` |
| API Latency (p99) | 99th percentile request duration | Prometheus: `histogram_quantile(0.99, http_request_duration_seconds)` |
| Error Rate | % of failed requests (HTTP 5xx) | Prometheus: `rate(http_requests_total{status=~"5.."}[5m])` |
| Search Latency (p95) | 95th percentile search duration | Prometheus: `search_duration_seconds` |
| Sync Success Rate | % of successful metadata syncs | Application metric: `sync_success_total / sync_total` |
| AI Response Latency | p95 AI response generation time | Application metric: `ai_response_latency_seconds` |
| Cache Hit Ratio | % of cache reads that hit | Prometheus: `cache_hits / (cache_hits + cache_misses)` |
| Queue Depth | Number of pending Celery tasks | Celery metric: `celery_queue_depth` |

## Service Level Objectives (SLOs)

### Tier 1: API (Critical Path)
| Metric | Target | Window | Budget |
|--------|--------|--------|--------|
| Availability | 99.9% | 30 days | 0.1% (43 min/month) |
| Latency p95 | < 500ms | 30 days | 5% of requests |
| Latency p99 | < 2s | 30 days | 1% of requests |
| Error Rate | < 0.1% | 30 days | 0.1% |

### Tier 2: Background Jobs
| Metric | Target | Window | Budget |
|--------|--------|--------|--------|
| Sync Availability | 99.5% | 30 days | 0.5% |
| Sync Latency (p95) | < 5 min per org | 30 days | 5% of syncs |
| AI Response Time (p95) | < 10s | 30 days | 5% of requests |

### Tier 3: Data & Cache
| Metric | Target | Window | Budget |
|--------|--------|--------|--------|
| Cache Hit Ratio | > 80% | 7 days | N/A |
| Database Query Time (p95) | < 100ms | 30 days | 5% of queries |
| Redis Availability | 99.9% | 30 days | 0.1% |

## Error Budgets

### Monthly Error Budget (99.9% availability)
- **Total**: 43 minutes 12 seconds of allowed downtime per month
- **Warning**: At 70% budget consumption (30 minutes)
- **Critical**: At 85% budget consumption (36 minutes)
- **Actions on budget depletion**:
  - Freeze all non-critical deployments
  - Require peer review for all changes
  - Mandatory load testing before deployment

## Recovery Objectives

| Objective | Target | Measurement |
|-----------|--------|-------------|
| RTO (Recovery Time Objective) | < 15 min | Time from incident detection to full recovery |
| RPO (Recovery Point Objective) | < 5 min | Maximum data loss in seconds |

## Performance Targets

| Operation | Target | Load |
|-----------|--------|------|
| API Requests/sec | 2,000 req/s | Per API pod |
| Search Queries/sec | 500 qps | Per search node |
| Metadata Sync (per org) | < 60 min | 10,000 components |
| AI Queries/sec | 50 qps | Per provider |
| Concurrent Users | 10,000 | Platform-wide |
| Active Organizations | 5,000 | Platform-wide |
