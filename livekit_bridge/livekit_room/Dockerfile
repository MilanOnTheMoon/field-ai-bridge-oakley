# Lightweight LiveKit room/SFU server for local testing.
# Upstream image is Alpine-based and already small (~30MB).
FROM livekit/livekit-server:latest

# 7880  - HTTP / WebSocket signaling
# 7881  - TCP WebRTC fallback (when UDP is blocked)
# 7882  - UDP WebRTC media (RTP/RTCP)
EXPOSE 7880/tcp 7881/tcp 7882/udp

# `--dev` gives the short api-secret + single-node defaults the README's
# tokens are wired against. Run with --network=host so the SFU is
# reachable on localhost from every other container on the same host.
COPY livekit.yaml /etc/livekit.yaml
ENTRYPOINT ["/livekit-server"]
CMD ["--dev", "--config", "/etc/livekit.yaml"]
