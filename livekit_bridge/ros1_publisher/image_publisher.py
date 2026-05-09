"""Thread 1: webcam (or static JPEG) → sensor_msgs/CompressedImage.

Stand-in for a real ROS1 camera driver. In production this whole file
would be replaced by `usb_cam`, `realsense2_camera`, etc., publishing
the same topic that thread 2 (livekit_bridge) subscribes to.

Runs in a worker thread spawned from main.py; expects rospy.init_node()
to have already been called by the parent process.
"""

import threading
from typing import Optional

import cv2
import rospy
from sensor_msgs.msg import CompressedImage


def run_image_publisher(
    topic: str,
    device: int,
    width: int,
    height: int,
    fps: int,
    stop: threading.Event,
    image_path: Optional[str] = None,
) -> None:
    """Publish JPEG-compressed frames on `topic` at `fps`.

    If `image_path` is given, replay that file forever (handy when no
    webcam is available). Otherwise capture from `device`.

    Exits cleanly when `stop` is set or rospy is shut down. Any opened
    camera is released in `finally` so re-running the script doesn't
    leave the device locked.
    """
    pub = rospy.Publisher(topic, CompressedImage, queue_size=1)
    rate = rospy.Rate(fps)

    # Exactly one of these is set after the if/else below; the publish
    # loop uses `cached` both as the static-image bytes AND as the
    # mode flag (None ⇒ pull a fresh frame from the webcam).
    cap = None
    cached: Optional[bytes] = None
    if image_path is not None:
        bgr = cv2.imread(image_path)
        if bgr is None:
            rospy.logerr(f"thread 1: could not read image file {image_path}")
            return
        # Encode once — the pixels never change, so re-encoding every
        # tick would just burn CPU.
        ok, jpg = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            rospy.logerr(f"thread 1: could not JPEG-encode {image_path}")
            return
        cached = jpg.tobytes()
        rospy.loginfo(f"thread 1: replaying {image_path} on {topic} at {fps} Hz")
    else:
        cap = cv2.VideoCapture(device)
        # Hint the driver — actual values may be clamped to whatever modes
        # the camera supports.
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_FPS, fps)
        if not cap.isOpened():
            rospy.logerr(f"thread 1: could not open camera device {device}")
            return
        rospy.loginfo(
            f"thread 1: publishing {topic} from device {device} at {width}x{height}@{fps}"
        )

    try:
        while not stop.is_set() and not rospy.is_shutdown():
            if cached is not None:
                # Static-image mode — reuse the bytes we encoded above.
                data = cached
            else:
                # Webcam mode — `assert` is for the type checker; the
                # if/else above guarantees one of `cached` / `cap` is set.
                assert cap is not None
                ok, bgr = cap.read()
                if not ok:
                    # Transient read failure (camera busy, frame dropped) —
                    # let the rate sleep avoid a hot loop.
                    rate.sleep()
                    continue
                # JPEG-encode in-process. Quality 80 is a good default for a
                # webcam — small payloads, no visible compression artefacts.
                ok, jpg = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if not ok:
                    continue
                data = jpg.tobytes()

            msg = CompressedImage()
            msg.header.stamp = rospy.Time.now()
            msg.header.frame_id = "camera"
            msg.format = "jpeg"
            msg.data = data
            pub.publish(msg)

            rate.sleep()
    finally:
        if cap is not None:
            cap.release()
        rospy.loginfo("thread 1: stopped")
