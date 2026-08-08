#!/usr/bin/env bash
# Runs the e2e OAuth flow tests inside a container on the sfir-network.
# Usage: run_e2e_oauth.sh [pytest args...]
set -e
cd "/home/faizan/projects/Salesforce-Inspector reloaded/backend"
docker run --rm --network sfir-network \
  -e SFIR_TEST_DATABASE_URL="postgresql+asyncpg://sfir:sfir@sfir-postgres:5432/sfir_test" \
  -e SFIR_TEST_REDIS_URL="redis://sfir-redis:6379/15" \
  -e UV_PROJECT_ENVIRONMENT=/tmp/venv \
  -v "$(pwd):/app" -w /app \
  ghcr.io/astral-sh/uv:python3.13-bookworm-slim \
  bash -lc "uv run --extra dev pytest $*"
