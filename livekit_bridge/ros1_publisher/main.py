"""ROS1 image-source node — webcam (or static JPEG) → ROS topic.

Standalone counterpart of the bridge in `ros1_livekit_bridge/`. The two
processes are wired together by ROS_MASTER_URI and a shared topic name.
In production, swap this whole component for a real ROS1 camera driver
(`usb_cam`, `realsense2_camera`, ...) — only the topic name has to match.

Configuration is YAML-only. Pass a path or rely on the default
`./config.yaml` next to this script:

    python main.py
    python main.py /path/to/my-config.yaml

Prerequisites
-------------
- ROS1 Noetic + `source /opt/ros/noetic/setup.bash`
- A `roscore` reachable at the `ros_master_uri` in the config
"""

import os
import signal
import sys
import threading
from pathlib import Path

import yaml


CONFIG_DEFAULT = Path(__file__).parent / "config.yaml"


def main() -> None:
    cfg_path = Path(sys.argv[1]) if len(sys.argv) > 1 else CONFIG_DEFAULT
    cfg = yaml.safe_load(cfg_path.read_text())

    # rospy reads ROS_MASTER_URI from the environment at init_node time, so
    # set it before the rospy import too — some rospy submodules cache the
    # value at import. setdefault lets `docker run -e ROS_MASTER_URI=...`
    # override the YAML default without needing a mounted config.
    os.environ.setdefault("ROS_MASTER_URI", cfg["ros_master_uri"])

    import rospy
    from image_publisher import run_image_publisher

    rospy.init_node(cfg["node_name"], anonymous=False, disable_signals=True)

    stop = threading.Event()
    thread = threading.Thread(
        target=run_image_publisher,
        args=(
            cfg["topic"],
            cfg["device"],
            cfg["width"],
            cfg["height"],
            cfg["fps"],
            stop,
        ),
        kwargs={"image_path": cfg.get("image_path")},
        name="ros1-image-publisher",
        daemon=True,
    )
    thread.start()
    rospy.loginfo(
        f"publisher running on {cfg['topic']} (master={os.environ['ROS_MASTER_URI']}) — Ctrl+C to stop"
    )

    try:
        signal.pause()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        rospy.signal_shutdown("user requested")
        thread.join(timeout=2)


if __name__ == "__main__":
    main()
