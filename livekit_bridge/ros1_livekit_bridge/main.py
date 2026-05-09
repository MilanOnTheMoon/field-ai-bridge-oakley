"""ROS1 → LiveKit bridge entrypoint.

Subscribes to a ROS1 image topic and forwards each frame into a LiveKit
room as a WebRTC video track. The ROS publisher this subscribes to lives
in `ros1_publisher/` (or any external ROS1 camera node — `usb_cam`,
`realsense2_camera`, etc.); they connect through the ROS master at
`ros_master_uri`.

The reusable component is `RosToLiveKitBridge` in `livekit_bridge.py`;
this file is just the YAML-config wiring around it.

Configuration is YAML-only. Pass a path or rely on the default
`./config.yaml` next to this script:

    python main.py
    python main.py /path/to/my-config.yaml

Prerequisites
-------------
- ROS1 Noetic + `source /opt/ros/noetic/setup.bash`
- A `roscore` reachable at the `ros_master_uri` in the config
- A LiveKit server reachable at `livekit.url`
"""

import os
import signal
import sys
from pathlib import Path

import yaml


CONFIG_DEFAULT = Path(__file__).parent / "config.yaml"


def main() -> None:
    cfg_path = Path(sys.argv[1]) if len(sys.argv) > 1 else CONFIG_DEFAULT
    cfg = yaml.safe_load(cfg_path.read_text())

    # rospy reads ROS_MASTER_URI from the environment at init_node time,
    # so set it before any rospy submodule is imported. setdefault lets
    # `docker run -e ROS_MASTER_URI=...` override the YAML default without
    # needing a mounted config.
    os.environ.setdefault("ROS_MASTER_URI", cfg["ros_master_uri"])

    import rospy
    from sensor_msgs.msg import CompressedImage, Image
    from livekit_bridge import (
        RosToLiveKitBridge,
        compressed_image_to_rgba,
        raw_image_to_rgba,
        mint_publisher_token,
    )

    # message_type → (rospy class, decoder). Add entries here for custom
    # image-shaped messages with their own decoders.
    msg_type, decoder = {
        "CompressedImage": (CompressedImage, compressed_image_to_rgba),
        "Image": (Image, raw_image_to_rgba),
    }[cfg["message_type"]]

    rospy.init_node(cfg["node_name"], anonymous=False, disable_signals=True)

    lk = cfg["livekit"]
    # LIVEKIT_URL env var lets a `docker run -e LIVEKIT_URL=...` override
    # the YAML default without mounting a custom config.
    livekit_url = os.environ.get("LIVEKIT_URL", lk["url"])
    token = mint_publisher_token(
        lk["api_key"],
        lk["api_secret"],
        lk["room"],
        lk["identity"],
    )
    bridge = RosToLiveKitBridge(
        url=livekit_url,
        token=token,
        msg_type=msg_type,
        decoder=decoder,
        width=cfg["width"],
        height=cfg["height"],
        track_name=lk["track_name"],
    )

    bridge.start(cfg["topic"])
    rospy.loginfo(
        f"bridge running (master={os.environ['ROS_MASTER_URI']}, livekit={livekit_url}) — Ctrl+C to stop"
    )

    try:
        signal.pause()
    except KeyboardInterrupt:
        pass
    finally:
        bridge.stop()
        rospy.signal_shutdown("user requested")


if __name__ == "__main__":
    main()
