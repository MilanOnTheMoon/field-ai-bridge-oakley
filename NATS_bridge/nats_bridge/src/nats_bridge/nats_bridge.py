#!/usr/bin/env python3
import rospy

from sensor_msgs.msg import NavSatFix
from nav_msgs.msg import Odometry

import math
import time
import os
import json
import asyncio
import uuid
import threading
import queue
from datetime import datetime, timezone

try:
    import nats
    from nats.errors import ConnectionClosedError, TimeoutError, NoServersError
    NATS_AVAILABLE = True
except ImportError:
    NATS_AVAILABLE = False

class nats_bridge(object):
    def __init__(self):
        # --- Configuration ---
        self._device_id = os.getenv('DEVICE_ID', 'unknownDevice')
        self.nats_server = os.getenv('NATS_SERVER_URL', 'nats://192.168.128.132:4223')

        # --- Rate Limiting ---
        try:
            self.target_rate = float(os.getenv('TELEMETRY_RATE', '2.0'))
        except ValueError:
            self.target_rate = 2.0

        self.min_pub_interval = 1.0 / self.target_rate if self.target_rate > 0 else 0
        self.last_pub_times = {}

        # --- NATS State ---
        self.nats_client = None
        self.publish_queue = queue.Queue(maxsize=100)
        self._stopping = False

        # --- Internal Robot State ---
        self.current_heading = 0.0
        self.last_gps_msg = None

        # --- Subscribers ---
        rospy.Subscriber('/gps/fix', NavSatFix, self._gps_callback, queue_size=10)                 # GPS callback
        rospy.Subscriber('/odometry/filtered', Odometry, self._odom_callback, queue_size=10)       # Odometry callback
        rospy.Subscriber('/battery', Odometry, self._power_callback, queue_size=10)                # Battery callback

        # --- NATS Setup ---
        if NATS_AVAILABLE:
            rospy.loginfo(f'NATS Bridge Online. Target Rate: {self.target_rate}Hz')
            self._setup_nats_thread()
        else:
            rospy.logerr('NATS library not installed.')

    def _should_publish(self, key):
        if self.min_pub_interval <= 0:
            return True
        now = time.time()
        last_time = self.last_pub_times.get(key, 0.0)
        if (now - last_time) >= self.min_pub_interval:
            self.last_pub_times[key] = now
            return True
        return False

    # =========================================
    # ROS1 Callbacks
    # =========================================

    def _gps_callback(self, msg):
        self.last_gps_msg = msg
        
        if not self._should_publish('gps'):
            return

        # FORCE SCALING: Always multiply by 1e7
        # The raw message is providing integers scaled down (e.g. 2.44e-06 instead of 24.4)
        lat = msg.latitude * 1e7
        lon = msg.longitude * 1e7

        payload = {
            "device_id": self._device_id,
            "ts": self._get_iso_timestamp(),
            "payload": {
                "current_position": {
                    "lat": lat,
                    "lon": lon,
                    "alt": msg.altitude
                },
                "gps_status": msg.status.status,
                "satellites": 0 
            }
        }
        self._queue_publish(f'{self._device_id}.telemetry.current_location', payload)

    def _power_callback(self, msg):
        if not self._should_publish('battery'):
            return

        voltage = msg.power_v
        current_amps = msg.bms_state.current / 1000.0
        soc = msg.bms_state.soc

        payload = {
            "device_id": self._device_id,
            "ts": self._get_iso_timestamp(),
            "payload": {
                "voltage_v": round(voltage, 2),
                "current_a": round(current_amps, 2),
                "remaining": int(soc),
                "cell_voltages": [v / 1000.0 for v in msg.bms_state.cell_vol if v > 0],
                "power_draw_w": round(abs(voltage * current_amps), 2)
            }
        }
        self._queue_publish(f'{self._device_id}.telemetry.battery_status', payload)

    def _odom_callback(self, msg):
        q = msg.pose.pose.orientation
        siny_cosp = 2 * (q.w * q.z + q.x * q.y)
        cosy_cosp = 1 - 2 * (q.y * q.y + q.z * q.z)
        yaw_rad = math.atan2(siny_cosp, cosy_cosp)
        
        correction_offset_rad = math.radians(180)
        yaw_rad = correction_offset_rad - yaw_rad
        self.current_heading = math.degrees(yaw_rad)
        if self.current_heading < 0:
            self.current_heading += 360

        if not self._should_publish('odom'):
            return

        alt = self.last_gps_msg.altitude if self.last_gps_msg else msg.pose.pose.position.z

        payload = {
            "device_id": self._device_id,
            "ts": self._get_iso_timestamp(),
            "payload": {
                "heading": self.current_heading,
                "velocity_x": msg.twist.twist.linear.x,
                "velocity_y": msg.twist.twist.linear.y,
                "altitude": alt
            }
        }
        self._queue_publish(f'{self._device_id}.telemetry.local_status', payload)

    # =========================================
    # NATS Logic
    # =========================================

    def _queue_publish(self, subject, data):
        if NATS_AVAILABLE:
            try:
                self.publish_queue.put_nowait((subject, data))
            except queue.Full:
                try:
                    self.publish_queue.get_nowait()
                    self.publish_queue.put_nowait((subject, data))
                except queue.Empty:
                    pass

    def _setup_nats_thread(self):
        self.nats_thread = threading.Thread(target=self._run_nats_loop, daemon=True)
        self.nats_thread.start()

    def _run_nats_loop(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._connect_nats())
        loop.run_until_complete(self._process_queue())

    async def _connect_nats(self):
        while not rospy.is_shutdown() and not self._stopping:
            try:
                self.nats_client = await nats.connect(
                    self.nats_server,
                    reconnect_time_wait=2,
                    max_reconnect_attempts=-1,
                    ping_interval=10
                )
                rospy.loginfo(f'Connected to NATS: {self.nats_server}')
                return
            except Exception as e:
                rospy.logwarn(f'NATS Connection failed: {e}. Retrying...')
                await asyncio.sleep(2)

    async def _process_queue(self):
        while not rospy.is_shutdown() and not self._stopping:
            try:
                try:
                    subject, data = self.publish_queue.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(0.01)
                    continue

                if self.nats_client and not self.nats_client.is_closed:
                    headers = {
                        "Nats-Msg-Id": uuid.uuid4().hex,
                        "sender": self._device_id,
                        "timeStamp": str(int(time.time_ns()))
                    }
                    await self.nats_client.publish(subject, json.dumps(data).encode(), headers=headers)
            except Exception as e:
                rospy.logerr(f'NATS Async Publish Error: {e}')
                await asyncio.sleep(1)

    def _get_iso_timestamp(self):
        return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
