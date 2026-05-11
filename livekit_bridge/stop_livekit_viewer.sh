#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="${LIVEKIT_VIEWER_CONTAINER_NAME:-ff-livekit-viewer}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed or not on PATH." >&2
  exit 1
fi

if docker ps --format '{{.Names}}' | grep -Fxq "${CONTAINER_NAME}"; then
  echo "Stopping ${CONTAINER_NAME}..."
  docker stop "${CONTAINER_NAME}" >/dev/null
fi

if docker ps -a --format '{{.Names}}' | grep -Fxq "${CONTAINER_NAME}"; then
  echo "Removing ${CONTAINER_NAME}..."
  docker rm "${CONTAINER_NAME}" >/dev/null
  echo "LiveKit viewer stopped."
else
  echo "No ${CONTAINER_NAME} container found."
fi
