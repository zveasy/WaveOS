#!/usr/bin/env bash
set -euo pipefail

METRICS_PORT="${METRICS_PORT:-9110}"
PROXY_HOST="${PROXY_HOST:-127.0.0.1}"
PROXY_PORT="${PROXY_PORT:-9000}"
TARGET_HOST="${TARGET_HOST:-example.com}"
TARGET_PORT="${TARGET_PORT:-80}"

export WAVEOS_METRICS_PORT="$METRICS_PORT"
export WAVEOS_PROXY_ENABLED=true
export WAVEOS_PROXY_MODE=http_forward
export WAVEOS_PROXY_LISTEN_HOST="$PROXY_HOST"
export WAVEOS_PROXY_LISTEN_PORT="$PROXY_PORT"
export WAVEOS_PROXY_TARGET_HOST="$TARGET_HOST"
export WAVEOS_PROXY_TARGET_PORT="$TARGET_PORT"

echo "Starting serve (metrics + proxy) on ports $METRICS_PORT / $PROXY_PORT"
waveos serve &
PID=$!
sleep 0.5

echo "Sending proxy request..."
curl -s -x "http://${PROXY_HOST}:${PROXY_PORT}" "http://${TARGET_HOST}/" >/dev/null || true

echo "Proxy metrics:"
curl -s "http://localhost:${METRICS_PORT}/metrics" | grep "waveos_proxy" || true

kill "$PID"
wait "$PID" 2>/dev/null || true
