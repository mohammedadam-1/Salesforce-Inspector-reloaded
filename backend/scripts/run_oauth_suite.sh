#!/usr/bin/env bash
set -e
cd "/home/faizan/projects/Salesforce-Inspector reloaded/backend"
uv run pytest tests/unit/test_salesforce.py tests/unit/test_oauth_session.py tests/integration/infrastructure/oauth_session/test_redis_oauth_session_repo.py -q 2>&1
