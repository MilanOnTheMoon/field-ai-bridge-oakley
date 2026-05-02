#!/usr/bin/env python

import rospy
import cv2
import json
import asyncio
import numpy as np
from aiohttp import web
from sensor_msgs.msg import Image
from cv_bridge import CvBridge

from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from av import VideoFrame

# A set to keep track of active WebRTC connections
pcs = set()

class ROSVideoTrack(VideoStreamTrack):
    """
    A WebRTC video track that reads frames from a ROS Image topic.
    """
    def __init__(self, topic_name):
        super().__init__()
        self.bridge = CvBridge()
        self.latest_frame = None
        
        # Subscribe to the ROS image topic
        self.sub = rospy.Subscriber(topic_name, Image, self.image_callback)
        rospy.loginfo(f"Subscribed to ROS topic: {topic_name}")

    def image_callback(self, msg):
        try:
            # Convert ROS Image message to OpenCV format (BGR8)
            cv_image = self.bridge.imgmsg_to_cv2(msg, "bgr8")
            self.latest_frame = cv_image
        except Exception as e:
            rospy.logerr(f"cv_bridge exception: {e}")

    async def recv(self):
        """
        This method is called by aiortc to grab the next video frame.
        """
        # Controls the framerate of the WebRTC stream
        pts, time_base = await self.next_timestamp()

        if self.latest_frame is not None:
            # Convert OpenCV image to av.VideoFrame for aiortc
            frame = VideoFrame.from_ndarray(self.latest_frame, format="bgr24")
        else:
            # If no frame has been received yet, send a black frame
            black_image = np.zeros((480, 640, 3), dtype=np.uint8)
            frame = VideoFrame.from_ndarray(black_image, format="bgr24")

        frame.pts = pts
        frame.time_base = time_base
        return frame

async def offer(request):
    """
    HTTP POST endpoint to handle the WebRTC SDP offer from the browser.
    """
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pcs.add(pc)

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        rospy.loginfo(f"Connection state is {pc.connectionState}")
        if pc.connectionState in ["failed", "closed"]:
            pcs.discard(pc)

    # Attach our custom ROS video track to the peer connection
    topic_name = rospy.get_param("~image_topic", "/camera/image_raw")
    video_track = ROSVideoTrack(topic_name)
    pc.addTrack(video_track)

    # Process the offer and generate an answer
    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.Response(
        content_type="application/json",
        text=json.dumps(
            {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
        ),
    )

async def on_shutdown(app):
    """
    Close all peer connections when the server shuts down.
    """
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()

def main():
    # disable_signals=True allows asyncio to handle Ctrl+C cleanly
    rospy.init_node("webrtc_image_streamer", disable_signals=True)
    
    port = rospy.get_param("~port", 8080)

    # Set up the aiohttp web server for WebRTC signaling
    app = web.Application()
    app.on_shutdown.append(on_shutdown)
    app.router.add_post("/offer", offer)

    rospy.loginfo(f"Starting WebRTC signaling server on http://0.0.0.0:{port}")
    
    # Run the asyncio web server (this blocks and runs the event loop)
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
