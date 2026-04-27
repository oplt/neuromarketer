#!/usr/bin/env bash
set -e

if redis-cli ping >/dev/null 2>&1; then
  echo "Redis already running on 6379"
  tail -f /dev/null
else
  echo "Starting Redis..."
  exec redis-server
fi