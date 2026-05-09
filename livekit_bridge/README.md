# ff_livekit_tests

![CI](https://github.com/hummlj/ff_livekit_tests/actions/workflows/ci.yml/badge.svg)

A reusable **ROS1 → LiveKit bridge** ([`ros1_livekit_bridge/`](ros1_livekit_bridge/)) plus the scaffolding to test it end-to-end on a single Ubuntu host. Drop the bridge into a robot to expose its camera as a WebRTC track in a LiveKit room.

## Components

The thing you ship:
- [`ros1_livekit_bridge/`](ros1_livekit_bridge/) — subscribes to a ROS image topic, publishes each frame as a LiveKit video track. Reusable building blocks live in [livekit_bridge.py](ros1_livekit_bridge/livekit_bridge.py).

Test scaffolding (none of this goes to the robot):
- [`livekit_room/`](livekit_room/) — local LiveKit SFU for development.
- [`ros1_publisher/`](ros1_publisher/) — stand-in camera driver that publishes `sensor_msgs/CompressedImage` (a webcam, or the bundled `polaris_image.jpg` looped at 30 Hz). Replace with your real camera node in production.
- [`viewer_livekit/`](viewer_livekit/) — browser viewer that subscribes to the room and shows the first incoming video track.
- [`streamer_livekit/`](streamer_livekit/) — standalone webcam → LiveKit publisher (no ROS). Useful as a sanity check that the SFU + viewer chain works.

The end-to-end test pipeline is: `ros1_publisher` → `roscore` → `ros1_livekit_bridge` → `livekit_room` → browser via `viewer_livekit`. Bring it up by working through steps 1–3 below.

---

## 1. Start the LiveKit room (`livekit_room/`)

Build once:
```bash
cd livekit_room
docker build -t ff-livekit-room .
```

Then pick the variant that matches who needs to reach the SFU:

**Local-only** — clients run on this same host:
```bash
docker run --rm --network=host ff-livekit-room \
    --dev --bind 0.0.0.0 --node-ip 127.0.0.1
```

**LAN-reachable** — other machines on the network need to reach the SFU:
```bash
docker run --rm \
    -p 7880:7880/tcp -p 7881:7881/tcp -p 7882:7882/udp \
    ff-livekit-room \
    --dev --bind 0.0.0.0 --node-ip <host-LAN-IP>     # e.g. 192.168.0.149
```

Three things matter in the LAN-reachable variant:
- **No `--network=host`.** Host-network ports go through the host firewall, which on Ubuntu blocks LAN inbound by default. Docker's `-p` punches holes via the `DOCKER` iptables chain instead — same path that already opens 8080 for the viewer.
- **`/udp` is mandatory** on `-p 7882:7882/udp`. Without it Docker publishes TCP only and silently drops the WebRTC media.
- **`--node-ip` is the IP the SFU advertises** in its ICE candidates. Every client (local browser, remote browser, sibling containers) must be able to dial it; the host's LAN IP works for all three because Docker DNATs inbound back to the container.

Clients connect with:

| | |
|---|---|
| **URL** | `ws://localhost:7880` (local-only) or `ws://<host-LAN-IP>:7880` (LAN-reachable) |
| **API key** | `devkey` |
| **API secret** | `secret` |

---

## 2. Start the viewer (`viewer_livekit/`)

The container mints a JWT and serves one HTML page; the browser runs on your host and talks WebRTC straight to the SFU. The viewer container is **never** in the media path.

```bash
cd viewer_livekit
docker build -t ff-livekit-viewer .

# Local-only SFU: defaults match (--url ws://localhost:7880).
docker run --rm -p 127.0.0.1:8080:8080 ff-livekit-viewer

# LAN-reachable SFU: --url must match the SFU's --node-ip from step 1.
# Drop the 127.0.0.1: prefix on -p so other machines can fetch the page.
docker run --rm -p 8080:8080 ff-livekit-viewer \
    --url ws://<host-LAN-IP>:7880
```

Then open `http://localhost:8080/` (or `http://<host-LAN-IP>:8080/` from another machine).

The `127.0.0.1:` prefix on `-p` keeps the JWT-bearing page on host loopback only — without it `-p 8080:8080` would expose the page (and the embedded JWT) on every interface. Drop the prefix only when you actually want LAN access.

The status chip in the top-left tells you what state the page is in:

- 🟡 `connecting…` — page just loaded, still negotiating with the SFU.
- 🟢 `connected, waiting for video…` — joined the room, no publisher yet. This is the "signaling works" indicator.
- 🟢 `streaming: TR_xxx` — first video track attached. End-to-end success.
- 🔴 `disconnected` / `error: …` — server dropped us, or token/connect failed.

---

## 3. Stream video into the room

Two ways. The bridge (3b) is what this repo exists for; the standalone (3a) is a smoke test that doesn't pull ROS into the loop.

### 3a. Standalone webcam streamer (`streamer_livekit/`) — sanity check

No ROS, no publisher container — just opens `/dev/video0` and pushes frames to the SFU. Use this to confirm the SFU + viewer chain works on its own.

```bash
cd streamer_livekit
docker build -t ff-livekit-streamer .

# Local-only SFU:
docker run --rm --network=host --device=/dev/video0 ff-livekit-streamer

# LAN-reachable SFU:
docker run --rm --network=host --device=/dev/video0 ff-livekit-streamer \
    --url ws://<host-LAN-IP>:7880
```

`--device=/dev/video0` is the host webcam passthrough (the *Docker* flag); `--device 1` as a *trailing* arg picks a different OpenCV index inside the container. The container runs as root so no host `video`-group membership is needed; just confirm the device exists with `ls -l /dev/video0`.

### 3b. ROS1 → LiveKit bridge (`ros1_livekit_bridge/`) — the main event

Three processes wired together by ROS:

1. `roscore` — the ROS master.
2. [`ros1_publisher/`](ros1_publisher/) — stand-in camera driver. Publishes `sensor_msgs/CompressedImage` on a topic. In production you'd delete this and let `usb_cam`, `realsense2_camera`, etc. publish the same topic.
3. [`ros1_livekit_bridge/`](ros1_livekit_bridge/) — subscribes to that topic and forwards each frame into the LiveKit room.

Two settings **must agree** between [`ros1_publisher/config.yaml`](ros1_publisher/config.yaml) and [`ros1_livekit_bridge/config.yaml`](ros1_livekit_bridge/config.yaml):

| Setting          | Purpose                                            |
|------------------|----------------------------------------------------|
| `ros_master_uri` | Both processes register with the same ROS master  |
| `topic`          | Publisher publishes on it, bridge subscribes to it |

The shipped defaults (`http://localhost:11311`, `/webcam/image/compressed`) work for the all-on-one-host Docker setup below. Edit the YAML files in place to change them.

#### Run with Docker (recommended)

Build the two images:
```bash
cd ros1_publisher        && docker build -t ff-ros1-publisher .
cd ../ros1_livekit_bridge && docker build -t ff-ros1-livekit-bridge .
```

All three ROS containers and the SFU share the host's network namespace via `--network=host`, so every peer is reachable on `localhost`. The YAML defaults already point at `localhost:11311` and `ws://localhost:7880`, so no `-e` plumbing is needed.

```bash
# Terminal 1 — roscore. Goes silent after "started core service [/rosout]";
# that's the ready signal, not a hang. Cold start has a ~5–10s pause first.
docker run --rm --network=host ros:noetic-ros-base roscore

# Terminal 2 — publisher. Defaults to looping the bundled polaris_image.jpg.
# For webcam capture: edit ros1_publisher/config.yaml (image_path: null) and
# add --device=/dev/video0 to the docker run.
docker run --rm --network=host ff-ros1-publisher

# Terminal 3 — bridge.
docker run --rm --network=host ff-ros1-livekit-bridge
```

Verify roscore from a fourth terminal if you want:
```bash
source /opt/ros/noetic/setup.bash && rostopic list
# expected: /rosout, /rosout_agg
```

To swap in a custom config without rebuilding the image, mount it:
```bash
docker run --rm --network=host \
    -v "$PWD/my-publisher.yaml:/app/config.yaml:ro" \
    ff-ros1-publisher
```

Expected log lines on a healthy startup:
```
# ros1_publisher
publisher running on /webcam/image/compressed (master=http://localhost:11311) — Ctrl+C to stop
thread 1: replaying polaris_image.jpg on /webcam/image/compressed at 30 Hz

# ros1_livekit_bridge
bridge running (master=http://localhost:11311, livekit=ws://localhost:7880) — Ctrl+C to stop
bridge: connected to LiveKit (track=camera)
bridge: publishing track sid=TR_…
bridge: subscribed to /webcam/image/compressed
```

The viewer (step 2) should now flip to green `streaming: TR_…` and show `polaris_image.jpg` (or your webcam frames). `Ctrl+C` to stop — each entrypoint `exec`s Python as PID 1, so SIGTERM lands cleanly.

#### Run on the host (Ubuntu 20.04 + ROS Noetic)

For tight dev iteration without container rebuilds. Four terminals:
```bash
# Terminal 1 — ROS master
source /opt/ros/noetic/setup.bash && roscore

# Terminal 2 — image publisher
source /opt/ros/noetic/setup.bash
cd ros1_publisher
pip install pyyaml opencv-python numpy rospkg defusedxml          # one-time
python main.py

# Terminal 3 — bridge
source /opt/ros/noetic/setup.bash
cd ros1_livekit_bridge
pip install pyyaml opencv-python numpy rospkg defusedxml livekit livekit-api   # one-time
python main.py
```

For OpenCV to read `/dev/video0` on the host, your user must be in the `video` group (the Docker path runs as root and skips this):
```bash
ls -l /dev/video0                                            # confirm device exists
groups | grep -q video || sudo usermod -aG video "$USER"     # then log out / back in
```
Skip entirely if `image_path` is set in `ros1_publisher/config.yaml`.

To use an external camera node instead of `ros1_publisher/`, point both configs at its topic — e.g. `topic: /usb_cam/image_raw/compressed`.

---

## 4. Drop the bridge into your robot

This is the whole point of the repo. Copy [`ros1_livekit_bridge/`](ros1_livekit_bridge/) verbatim, point its `config.yaml` at your existing camera topic and your production LiveKit server, done.

The reusable building blocks in [livekit_bridge.py](ros1_livekit_bridge/livekit_bridge.py):

- **`RosToLiveKitBridge`** — the bridge class. `start(topic)` / `stop()` lifecycle; parameterized by `msg_type` and a `decoder` callable so it works with any image-shaped ROS message.
- **`compressed_image_to_rgba`** and **`raw_image_to_rgba`** — reference decoders for `sensor_msgs/CompressedImage` and `sensor_msgs/Image`. Write your own with the signature `(msg, width, height) -> bytes | None` to support custom message types.
- **`mint_publisher_token`** — convenience JWT helper for setups where the API secret lives on the robot. **In production, hand the bridge a token your backend issued instead** — that way the robot never holds the secret.

[main.py](ros1_livekit_bridge/main.py) is the YAML-config wiring; treat it as a small worked example of using the three pieces together.

The container is already production-shaped: pinned base image, deps installed in a separate layer, source copied last, entrypoint `exec`s Python as PID 1 for clean signal handling.

---

## Network topology

Five components, three flows:

- **HTTP (8080)** — host browser fetches one HTML page from the viewer container; the page has a subscribe-only JWT baked in.
- **WebSocket signaling (7880)** — every LiveKit client (browser, streamer, ROS bridge) negotiates with the SFU.
- **WebRTC media (UDP 7882, TCP 7881 fallback)** — publishers push frames into the SFU; subscribers pull them out. The SFU forwards; no peer-to-peer media.
- **ROS1 (11311 + ephemeral TCPROS)** — publisher and bridge register with `roscore` and exchange `CompressedImage` over TCPROS.

```
   ┌────────────────────────┐
   │  streamer_livekit      │ ─── ws 7880 (sig) ───┐
   │  webcam → I420 → track │ ─── udp 7882 ────────┤
   └────────────────────────┘     (or tcp 7881)    │
                                                   │
   ┌────────────────────────┐  ROS topic           │
   │  ros1_publisher        │  /webcam/image/      │
   │  webcam / static JPEG  │  compressed          │
   └────────────────────────┘ ─────────┐           │
                                       ▼           │
                                ┌──────────────┐   │
                                │  roscore     │   │
                                │  :11311      │   │
                                └──────┬───────┘   │
                                       │ ROS topic │
                                       ▼           │
   ┌────────────────────────┐                      │
   │  ros1_livekit_bridge   │ ─── ws 7880 (sig) ───┤
   │  decode → RGBA → track │ ─── udp 7882 ────────┤
   └────────────────────────┘     (or tcp 7881)    ▼
                                       ┌──────────────────────────┐
                                       │  livekit_room (SFU)      │
                                       │  --dev: devkey / secret  │
                                       │  node_ip = 127.0.0.1     │
                                       │  fans media to all       │
                                       │    subscribers           │
                                       └──────────┬───────────────┘
                                                  │ ws 7880 (sig)
                                                  │ udp 7882 (media)
                                                  ▼
   ┌────────────────────────┐  HTTP 8080  ┌──────────────────────┐
   │  viewer_livekit        │  HTML+JWT   │  host browser        │
   │  HTTP server +         │ ──────────► │  livekit-client UMD  │
   │  JWT mint (sub-only)   │             │  attaches first      │
   │                        │             │  remote video track  │
   └────────────────────────┘             └──────────────────────┘
```

The `node_ip` shown is the local-only flow. For LAN-reachable use, the SFU runs without `--network=host` and `node_ip = <host-LAN-IP>` (see step 1's LAN variant). For internet-facing deploys, point `--node-ip` at the host's public IP and update every client's `LIVEKIT_URL` to match.

## Ports

| Port        | Owner            | Purpose                                                     |
|-------------|------------------|-------------------------------------------------------------|
| `7880/tcp`  | `livekit_room`   | HTTP/WebSocket signaling — every LiveKit client connects here |
| `7881/tcp`  | `livekit_room`   | WebRTC TCP fallback when UDP is blocked                     |
| `7882/udp`  | `livekit_room`   | WebRTC media (RTP/RTCP) — the hot path                      |
| `8080/tcp`  | `viewer_livekit` | Serves the viewer page; pin to `127.0.0.1` since the page carries a JWT |
| `11311/tcp` | `roscore`        | ROS master; publisher and bridge both register here. Address from each component's `ros_master_uri`. |

## Trust / auth model

- The **API secret** (`secret` in `--dev`) lives only on services that mint tokens — the viewer (subscribe-only), the streamer, and the ROS bridge (publish-only). It must never reach the browser.
- The LiveKit server validates JWTs locally against the shared HMAC secret — no callback to the issuing service. So *where the secret lives* matters more than *who issues the token*.
- The browser only ever sees a JWT, embedded in the HTML page served by `viewer_livekit`. Anyone who can reach port 8080 reads that JWT, which is why the viewer's `-p` defaults to `127.0.0.1:8080:8080`.
- **For production:** replace `mint_publisher_token` with a token your backend issued and pass it straight to `RosToLiveKitBridge`. The robot then never holds the API secret.

---

## Resources

- [LiveKit Documentation](https://docs.livekit.io/)
- [LiveKit Python SDK](https://github.com/livekit/python-sdks)
