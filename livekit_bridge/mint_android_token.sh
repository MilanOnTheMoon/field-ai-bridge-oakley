#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="${LIVEKIT_VIEWER_IMAGE_NAME:-ff-livekit-viewer}"
ROOM="${LIVEKIT_ROOM:-test-room}"
IDENTITY="${LIVEKIT_ANDROID_IDENTITY:-android-oakley}"
API_KEY="${LIVEKIT_API_KEY:-devkey}"
API_SECRET="${LIVEKIT_API_SECRET:-secret}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed or not on PATH." >&2
  exit 1
fi

if ! docker image inspect "${IMAGE_NAME}" >/dev/null 2>&1; then
  echo "Building ${IMAGE_NAME}..."
  docker build -t "${IMAGE_NAME}" "${SCRIPT_DIR}/viewer_livekit" >/dev/null
fi

TOKEN="$(
  docker run --rm --entrypoint python "${IMAGE_NAME}" - "${API_KEY}" "${API_SECRET}" "${ROOM}" "${IDENTITY}" <<'PY'
import sys
from livekit import api

api_key, api_secret, room, identity = sys.argv[1:]
token = (
    api.AccessToken(api_key, api_secret)
    .with_identity(identity)
    .with_grants(
        api.VideoGrants(
            room_join=True,
            room=room,
            can_publish=True,
            can_subscribe=False,
        )
    )
    .to_jwt()
)
print(token)
PY
)"

if command -v pbcopy >/dev/null 2>&1; then
  printf "%s" "${TOKEN}" | pbcopy
  COPIED="yes"
else
  COPIED="no"
fi

echo "${TOKEN}"
echo
echo "Room: ${ROOM}"
echo "Identity: ${IDENTITY}"
if [[ "${COPIED}" == "yes" ]]; then
  echo "Copied to clipboard."
else
  echo "pbcopy not found; copy the token printed above."
fi
