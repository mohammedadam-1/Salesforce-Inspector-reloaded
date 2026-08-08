#!/usr/bin/env bash
set -e
cd "/home/faizan/projects/Salesforce-Inspector reloaded/backend"
echo "=== UNIT TESTS ==="
uv run pytest tests/unit/ -q 2>&1
echo "=== INTEGRATION TESTS ==="
uv run pytest tests/integration/ -q 2>&1
echo "=== OAUTH TESTS ==="
uv run pytest tests/unit/test_salesforce.py tests/unit/test_oauth_session.py tests/integration/infrastructure/oauth_session/test_redis_oauth_session_repo.py -q 2>&1
