"""Lean LiveKit webcam streamer.

Opens the local webcam with OpenCV, joins a LiveKit room, and publishes
the camera as a WebRTC video track. Symmetric counterpart to
`viewer_livekit/main.py`: one publishes, the other subscribes.

Configuration: CLI flags only — no env vars, no config files. All flags
have sensible defaults that match the dev LiveKit container in
`livekit_room/Dockerfile` (running with `--dev`), so the bare command
just works against a local dev server.

Run as a container — see `Dockerfile`. Trailing args after the image
name pass through to this script:

    docker build -t ff-livekit-streamer .
    docker run --rm --network=host --device=/dev/video0 ff-livekit-streamer
    docker run --rm --network=host --device=/dev/video0 ff-livekit-streamer \\
        --url ws://1.2.3.4:7880 --room my-room --identity bob

`--device=/dev/video0` is the host webcam passthrough; `--device 1` (a
trailing flag) selects a different OpenCV camera index inside the
container. OpenCV uses V4L2; no display server required.
"""

import argparse
import asyncio
import signal

import cv2
from livekit import api, rtc


# Hardcoded capture parameters. Easy to bump; not worth a CLI flag for a
# test rig — actual camera output may be clamped to the closest mode the
# device supports.
WIDTH, HEIGHT, FPS = 1920, 1080, 30


def make_token(api_key: str, api_secret: str, room: str, identity: str) -> str:
    """Mint a publish-only JWT scoped to one room.

    `can_subscribe=False` means this script never decodes other
    participants' video — pure publisher hygiene, mirrors the viewer's
    subscribe-only token.
    """
    return (
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


async def stream(
    url: str, token: str, device: int, width: int, height: int, fps: int
) -> None:
    """Connect, publish a camera track, pump frames until cancelled.

    Cancellation (e.g. via SIGINT/SIGTERM, see `main`) raises
    CancelledError inside `asyncio.sleep`, which falls through to the
    `finally` block so we always release the camera and disconnect cleanly.
    """
    room = rtc.Room()
    await room.connect(url, token)
    print(f"connected: room={room.name} identity={room.local_participant.identity}")

    # Build a video track backed by a VideoSource we feed frames into.
    source = rtc.VideoSource(width, height)
    track = rtc.LocalVideoTrack.create_video_track("camera", source)
    options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_CAMERA)
    publication = await room.local_participant.publish_track(track, options)
    print(f"publishing: sid={publication.sid}")

    cap = cv2.VideoCapture(device)
    # Hint the driver — actual values may be clamped to what the camera supports.
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)
    if not cap.isOpened():
        await room.disconnect()
        raise RuntimeError(f"could not open webcam device {device}")

    try:
        while True:
            ok, bgr = cap.read()
            if not ok:
                # Transient read failure (camera busy, frame dropped) — back off briefly.
                await asyncio.sleep(0.05)
                continue
            # cap.read() blocks at the camera's native frame rate, so it
            # paces the loop on its own — adding our own sleep on top
            # would halve the effective FPS and let frames age in the
            # driver buffer.
            #
            # I420 (one cvtColor) is what the encoder consumes; sending
            # RGBA would force the SDK to do another full-frame
            # conversion before encoding.
            i420 = cv2.cvtColor(bgr, cv2.COLOR_BGR2YUV_I420)
            frame = rtc.VideoFrame(
                width, height, rtc.VideoBufferType.I420, i420.tobytes()
            )
            source.capture_frame(frame)
    finally:
        cap.release()
        await room.disconnect()


def main() -> None:
    """Parse args, mint a publisher token, run the async streaming loop."""
    parser = argparse.ArgumentParser(
        description="Lean LiveKit webcam streamer.",
        # Auto-appends "(default: ...)" to every flag's help line.
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    # --- Connection: defaults match livekit_room/ running in --dev mode. ---
    parser.add_argument(
        "--url", default="ws://localhost:7880", help="LiveKit server WebSocket URL"
    )
    parser.add_argument(
        "--api-key",
        default="devkey",
        help="LiveKit API key (the --dev server hardcodes 'devkey')",
    )
    parser.add_argument(
        "--api-secret",
        default="secret",
        help="LiveKit API secret (the --dev server hardcodes 'secret')",
    )
    # --- Room / identity: matches the viewer's defaults so they meet up. ---
    parser.add_argument("--room", default="test-room", help="Room name to join")
    parser.add_argument(
        "--identity",
        default="streamer",
        help="Participant identity shown to other peers",
    )
    # --- Capture device. ---
    parser.add_argument(
        "--device",
        type=int,
        default=0,
        help="OpenCV camera index (0 = first/built-in webcam)",
    )
    args = parser.parse_args()

    token = make_token(args.api_key, args.api_secret, args.room, args.identity)

    loop = asyncio.new_event_loop()
    task = loop.create_task(stream(args.url, token, args.device, WIDTH, HEIGHT, FPS))
    # Cancel the task on Ctrl+C / SIGTERM so the `finally` in stream()
    # runs and we leave the room cleanly instead of dropping the connection.
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, task.cancel)
    try:
        loop.run_until_complete(task)
    except asyncio.CancelledError:
        pass
    finally:
        loop.close()


if __name__ == "__main__":
    main()
