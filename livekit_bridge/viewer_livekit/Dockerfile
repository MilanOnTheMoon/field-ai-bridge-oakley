# Browser-based LiveKit viewer.
#
# What runs where:
#   - This container runs a tiny HTTP server that mints a JWT (using the
#     LiveKit API secret) and serves one HTML page.
#   - The user's *browser on the host* loads that page, then talks WebRTC
#     directly to the LiveKit server — the container is not in the media
#     path. So the only port that needs publishing is 8080 (HTTP).
#   - `--url` is the URL the *browser* uses to reach LiveKit, not the
#     container. `ws://localhost:7880` works when LiveKit's container
#     publishes 7880 on the host.
#
# Security: the page embeds a signed JWT scoped to your room. Anyone who
# can reach the published port reads it. The default Docker publish
# (`-p 8080:8080`) binds to 0.0.0.0 on the host, exposing the page to
# your LAN. Pin to host loopback unless you really mean to share:
#
#     docker build -t ff-livekit-viewer .
#     docker run --rm -p 127.0.0.1:8080:8080 ff-livekit-viewer
#
# Then open http://localhost:8080/ in your browser.
#
# Connect to a remote LiveKit server (the URL is what the *browser* will
# use, so it must be reachable from your host):
#
#     docker run --rm -p 127.0.0.1:8080:8080 ff-livekit-viewer \
#         --url ws://livekit.example.com
FROM python:3.12-slim

WORKDIR /app

# Install Python deps first so editing source doesn't bust the dep layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Documentation only — `docker run` still needs `-p` to actually publish.
EXPOSE 8080

# `--bind 0.0.0.0` so the published port reaches main.py (the default
# 127.0.0.1 inside the container is unreachable from the host).
# `--no-open` because there's no browser or display in the container.
# Trailing args from `docker run … <flags>` pass through to main.py.
ENTRYPOINT ["python", "-u", "main.py", "--bind", "0.0.0.0", "--no-open"]
CMD []
