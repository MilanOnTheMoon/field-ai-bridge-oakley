"""Generic ROS1 → LiveKit video bridge.

Forward one ROS1 image topic into a LiveKit room as a WebRTC video
track. Decoupled from token issuance, message type, and decoder so the
same component works for any image-shaped ROS message — JPEG-compressed
camera feeds, raw `sensor_msgs/Image`, depth maps you've coloured into
RGB, etc.

Typical use
-----------
    from sensor_msgs.msg import CompressedImage
    from livekit_bridge import (
        RosToLiveKitBridge, compressed_image_to_rgba, mint_publisher_token,
    )

    rospy.init_node("my_robot_bridge")          # caller owns the node

    token = mint_publisher_token(API_KEY, API_SECRET, "room", "robot-cam")
    # …or hand it a token your backend already issued — the bridge
    # doesn't care where it came from.

    bridge = RosToLiveKitBridge(
        url="ws://localhost:7880",          # wss://… for production
        token=token,
        msg_type=CompressedImage,
        decoder=compressed_image_to_rgba,
        width=640, height=480,
        track_name="camera",
    )
    bridge.start("/camera/image_raw/compressed")
    try:
        rospy.spin()
    finally:
        bridge.stop()

Plugging in a different image type
----------------------------------
Write a decoder with this signature:

    def my_decoder(msg, target_width, target_height) -> bytes | None:
        # return RGBA bytes (4 * target_width * target_height), or None to drop

then pass it as `decoder=` along with the matching `msg_type=`.
`compressed_image_to_rgba` and `raw_image_to_rgba` below are reference
implementations.

Threading
---------
`start()` spawns a worker thread that runs an asyncio event loop. The
loop owns the LiveKit `Room`. The rospy subscriber callback runs on
rospy's internal worker threads — `VideoSource.capture_frame` is sync
and thread-safe, so we never have to bridge back to the asyncio loop.

The caller is responsible for `rospy.init_node()` (rospy enforces one
node per process) and for `rospy.spin()` or whatever main-thread block
suits the application.
"""

import asyncio
import threading
from typing import Any, Callable, Optional, Type

import cv2
import numpy as np
import rospy
from sensor_msgs.msg import CompressedImage, Image
from livekit import api, rtc


# A decoder converts one ROS message into RGBA bytes of size exactly
# 4 * target_width * target_height. Return None to drop the frame
# (unsupported encoding, decode failure, etc.).
Decoder = Callable[[Any, int, int], Optional[bytes]]


def mint_publisher_token(
    api_key: str, api_secret: str, room: str, identity: str
) -> str:
    """Mint a publish-only JWT for a bridge.

    Convenience for setups where the robot has the LiveKit API
    secret on-box (e.g. local dev). For real deployments, have your
    backend issue tokens and pass them straight to `RosToLiveKitBridge`.
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


def compressed_image_to_rgba(
    msg: CompressedImage, width: int, height: int
) -> Optional[bytes]:
    """Decode `sensor_msgs/CompressedImage` (JPEG/PNG) → RGBA bytes."""
    bgr = cv2.imdecode(np.frombuffer(msg.data, np.uint8), cv2.IMREAD_COLOR)
    if bgr is None:
        rospy.logwarn_throttle(
            5.0,
            f"compressed_image_to_rgba: cv2.imdecode failed (format={msg.format!r})",
        )
        return None
    if (bgr.shape[1], bgr.shape[0]) != (width, height):
        bgr = cv2.resize(bgr, (width, height))
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGBA).tobytes()


def raw_image_to_rgba(msg: Image, width: int, height: int) -> Optional[bytes]:
    """Convert `sensor_msgs/Image` (rgb8/bgr8/mono8) → RGBA bytes.

    Other encodings are dropped with a throttled warning. Extend the
    if/elif ladder for whatever your camera publishes.
    """
    arr = np.frombuffer(msg.data, dtype=np.uint8)
    if msg.encoding == "rgb8":
        rgba = cv2.cvtColor(arr.reshape((msg.height, msg.width, 3)), cv2.COLOR_RGB2RGBA)
    elif msg.encoding == "bgr8":
        rgba = cv2.cvtColor(arr.reshape((msg.height, msg.width, 3)), cv2.COLOR_BGR2RGBA)
    elif msg.encoding == "mono8":
        rgba = cv2.cvtColor(arr.reshape((msg.height, msg.width)), cv2.COLOR_GRAY2RGBA)
    else:
        rospy.logwarn_throttle(
            5.0, f"raw_image_to_rgba: unsupported encoding {msg.encoding!r}"
        )
        return None
    if (rgba.shape[1], rgba.shape[0]) != (width, height):
        rgba = cv2.resize(rgba, (width, height))
    return rgba.tobytes()


class RosToLiveKitBridge:
    """Forward one ROS image topic into a LiveKit room as a video track.

    Lifecycle:
        bridge = RosToLiveKitBridge(url=..., token=..., msg_type=...,
                                    decoder=..., width=..., height=...)
        bridge.start("/some/topic")     # spawns the worker thread
        ...                             # main thread does whatever
        bridge.stop()                   # signal shutdown + join

    The bridge itself doesn't know anything about webcams, JPEG, or
    token issuance — those are caller-side concerns. That's the whole
    point of this refactor.
    """

    def __init__(
        self,
        *,
        url: str,
        token: str,
        msg_type: Type,
        decoder: Decoder,
        width: int,
        height: int,
        track_name: str = "camera",
    ) -> None:
        """Configure the bridge. Doesn't connect or subscribe yet — call `start()`.

        Args:
            url: LiveKit server WebSocket URL (e.g. ``wss://livekit.example.com``
                or ``ws://localhost:7880`` for the dev server).
            token: A LiveKit JWT with publish rights for the target room.
                Use `mint_publisher_token` for local dev, or hand in one
                your backend issued.
            msg_type: The ROS message class the bridge will subscribe to,
                e.g. ``sensor_msgs.msg.CompressedImage`` or
                ``sensor_msgs.msg.Image``. Must match what `decoder` expects.
            decoder: Callable that turns one `msg_type` instance into RGBA
                bytes of size exactly ``4 * width * height`` (or returns
                None to drop the frame). See `compressed_image_to_rgba` /
                `raw_image_to_rgba` for reference implementations.
            width: Output frame width in pixels. The decoder is responsible
                for resizing inbound frames to this exact size — LiveKit's
                `VideoSource` is created at this resolution and won't accept
                anything else.
            height: Output frame height in pixels. Same constraint as `width`.
            track_name: Name attached to the published WebRTC track. Shows
                up in viewer SDKs / `room.remote_participants[*].track_publications`
                so peers can pick the right feed when there are multiple.
        """
        self._url = url
        self._token = token
        self._msg_type = msg_type
        self._decoder = decoder
        self._width = width
        self._height = height
        self._track_name = track_name

        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._topic: Optional[str] = None

    def start(self, topic: str) -> None:
        """Start subscribing to `topic` and forwarding frames into the room.

        Spawns one worker thread (named `ros1-subscriber-and-livekit-publisher`).
        """
        if self._thread is not None:
            raise RuntimeError("bridge already started")
        self._topic = topic
        self._thread = threading.Thread(
            target=self._run_loop,
            name="ros1-subscriber-and-livekit-publisher",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Signal shutdown; the worker releases the room and exits cleanly."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        asyncio.run(self._run_async())

    async def _run_async(self) -> None:
        room = rtc.Room()
        await room.connect(self._url, self._token)
        rospy.loginfo(f"bridge: connected to LiveKit (track={self._track_name})")

        source = rtc.VideoSource(self._width, self._height)
        track = rtc.LocalVideoTrack.create_video_track(self._track_name, source)
        options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_CAMERA)
        publication = await room.local_participant.publish_track(track, options)
        rospy.loginfo(f"bridge: publishing track sid={publication.sid}")

        # Captured for the closure: width, height, source, decoder.
        width, height = self._width, self._height
        decoder = self._decoder

        def on_msg(msg: Any) -> None:
            # Runs on a rospy worker thread. capture_frame is sync + thread-safe.
            rgba = decoder(msg, width, height)
            if rgba is None:
                return
            source.capture_frame(
                rtc.VideoFrame(width, height, rtc.VideoBufferType.RGBA, rgba)
            )

        sub = rospy.Subscriber(self._topic, self._msg_type, on_msg, queue_size=1)
        rospy.loginfo(f"bridge: subscribed to {self._topic}")

        try:
            while not self._stop.is_set() and not rospy.is_shutdown():
                await asyncio.sleep(0.1)
        finally:
            sub.unregister()
            await room.disconnect()
            rospy.loginfo("bridge: stopped")
