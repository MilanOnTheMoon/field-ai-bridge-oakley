#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="${LIVEKIT_VIEWER_IMAGE_NAME:-ff-livekit-viewer}"
CONTAINER_NAME="${LIVEKIT_VIEWER_CONTAINER_NAME:-ff-livekit-viewer}"
NODE_IP="${LIVEKIT_NODE_IP:-}"
ROOM="${LIVEKIT_ROOM:-test-room}"
PORT="${LIVEKIT_VIEWER_PORT:-8080}"

detect_node_ip() {
  if command -v ipconfig >/dev/null 2>&1 && command -v route >/dev/null 2>&1; then
    local interface
    interface="$(route get default 2>/dev/null | awk '/interface:/{print $2; exit}')"
    if [[ -n "${interface}" ]]; then
      ipconfig getifaddr "${interface}" 2>/dev/null || true
      return
    fi
  fi

  if command -v hostname >/dev/null 2>&1; then
    hostname -I 2>/dev/null | awk '{print $1}' || true
  fi
}

if [[ -z "${NODE_IP}" ]]; then
  NODE_IP="$(detect_node_ip)"
fi

if [[ -z "${NODE_IP}" ]]; then
  echo "Could not detect a LAN IP. Re-run with LIVEKIT_NODE_IP=<ip>." >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed or not on PATH." >&2
  exit 1
fi

echo "Building ${IMAGE_NAME}..."
docker build -t "${IMAGE_NAME}" "${SCRIPT_DIR}/viewer_livekit"

if docker ps --format '{{.Names}}' | grep -Fxq "${CONTAINER_NAME}"; then
  echo "Stopping existing ${CONTAINER_NAME}..."
  docker stop "${CONTAINER_NAME}" >/dev/null
fi

if docker ps -a --format '{{.Names}}' | grep -Fxq "${CONTAINER_NAME}"; then
  echo "Removing old ${CONTAINER_NAME}..."
  docker rm "${CONTAINER_NAME}" >/dev/null
fi

echo "Starting LiveKit viewer for room ${ROOM}..."
docker run -d \
  --name "${CONTAINER_NAME}" \
  -p "${PORT}:8080" \
  "${IMAGE_NAME}" \
  --url "ws://${NODE_IP}:7880" \
  --room "${ROOM}" \
  --bind 0.0.0.0 \
  --port 8080 \
  --no-open >/dev/null

echo
echo "LiveKit viewer is running."
echo "Viewer URL on this computer: http://localhost:${PORT}/"
echo "Viewer URL on LAN: http://${NODE_IP}:${PORT}/"
echo "LiveKit URL: ws://${NODE_IP}:7880"
echo "Room: ${ROOM}"
echo
echo "Logs: docker logs -f ${CONTAINER_NAME}"
