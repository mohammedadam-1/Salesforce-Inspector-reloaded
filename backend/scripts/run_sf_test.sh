#!/usr/bin/env bash
set -e
cd "/home/faizan/projects/Salesforce-Inspector reloaded/backend"
uv run pytest tests/unit/test_salesforce.py -q 2>&1
