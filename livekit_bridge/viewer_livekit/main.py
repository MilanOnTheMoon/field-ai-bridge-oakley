"""Lean browser-based LiveKit viewer.

Mints a subscribe-only access token with the LiveKit server SDK, serves a
self-contained HTML page on 127.0.0.1, and opens the user's default
browser. The page loads `livekit-client` from a CDN, joins the room, and
attaches the first incoming remote video track to a full-screen
`<video>` element.

Why a browser instead of a Python GUI: zero GUI deps, works on any OS,
and the browser already has a battle-tested WebRTC stack. The Python
process is only here to mint the JWT (which needs the API secret that
the browser must never see) and serve one static page.

Configuration: CLI flags only — no env vars, no config files. All flags
have sensible defaults that match the dev LiveKit container in
`livekit_room/dockerfile` (running with `--dev`), so `python main.py`
just works against a local dev server.

Usage:
    python main.py                                # dev defaults (localhost)
    python main.py --url ws://1.2.3.4:7880        # remote LiveKit server
    python main.py --room my-room --identity bob  # custom room / name
    python main.py --port 9090 --no-open          # custom port, no browser

Run `python main.py --help` to see every flag with its default.

Or run as a container — see `Dockerfile`. The container entrypoint
sets `--bind 0.0.0.0 --no-open` so the published port is reachable
from a browser on the host; everything else is unchanged.
"""

import argparse
import http.server
import json
import socketserver
import threading
import webbrowser
from urllib.parse import parse_qs, urlparse

from livekit import api


# Single-page HTML served to the browser. {url}, {token}, {room} are
# filled in by str.format with !r repr so they end up as properly
# escaped JS strings. All literal CSS/JS braces are doubled ({{ }}) so
# str.format leaves them alone.
#
# The <video> tag is muted + playsinline so the browser autoplay policy
# allows playback without a user gesture (this room is video-only, so
# muting costs nothing). livekit-client v2 UMD is loaded from jsdelivr;
# fully offline use would require vendoring the bundle locally.
#
# Name our globals away from built-ins: top-level `let`/`const` in a
# classic <script> share a lexical environment with every other script
# on the page, so a `const URL = "..."` here would shadow the built-in
# `URL` constructor that livekit-client calls via `new URL(t)` —
# producing `"ws://..." is not a constructor`. `LIVEKIT_URL` is safe.
HTML_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><title>LiveKit Viewer — {room}</title>
<style>
  html,body{{margin:0;background:#111;color:#eee;font-family:system-ui;height:100%}}
  #status{{position:fixed;top:8px;left:8px;padding:6px 10px;background:#0008;border-radius:4px;font-size:12px;line-height:1.4;z-index:1;max-width:90vw}}
  #parts-head{{opacity:0.75;font-size:11px;margin-top:2px}}
  #parts-list{{list-style:none;padding:0;margin:4px 0 0 0;font-size:11px}}
  #parts-list li{{opacity:0.75;line-height:1.4}}
  #parts-list li::before{{content:"";display:inline-block;width:5px;height:5px;border-radius:50%;background:#aaa;margin-right:6px;vertical-align:middle}}
  #parts-list li.self{{opacity:1;font-weight:600}}
  #parts-list li.self::before{{background:#4caf50}}
  #gps{{margin-top:6px;padding-top:6px;border-top:1px solid #fff2;color:#c7f9d4;font-size:11px;white-space:pre-line}}
  #dot{{display:inline-block;width:8px;height:8px;border-radius:50%;background:#888;margin-right:6px;vertical-align:middle;transition:background 120ms}}
  #dot.connecting{{background:#e6c14f}}
  #dot.connected{{background:#4caf50}}
  #dot.error{{background:#e25d5d}}
  video{{width:100vw;height:100vh;object-fit:contain;background:#000;display:block}}
</style></head>
<body>
<div id="status"><div id="state"><span id="dot" class="connecting"></span><span id="state-label">connecting…</span></div><div id="parts-head"></div><ul id="parts-list"></ul><div id="gps">GPS: waiting…</div></div>
<video id="v" autoplay playsinline muted></video>
<script src="https://cdn.jsdelivr.net/npm/livekit-client@2/dist/livekit-client.umd.min.js"></script>
<script>
  const LIVEKIT_URL = {url!r}, LIVEKIT_TOKEN = {token!r};
  const dotEl = document.getElementById('dot');
  const stateLabelEl = document.getElementById('state-label');
  const partsHeadEl = document.getElementById('parts-head');
  const partsListEl = document.getElementById('parts-list');
  const gpsEl = document.getElementById('gps');
  const videoEl = document.getElementById('v');
  let attached = false;
  const room = new LivekitClient.Room({{ adaptiveStream: true, dynacast: true }});

  // Drives the colored dot + label together so the visible state and
  // dot color can never disagree. `kind` is one of 'connecting',
  // 'connected', 'error' (matches the CSS classes for #dot).
  function setState(kind, label) {{
    dotEl.className = kind;
    stateLabelEl.textContent = label;
  }}

  // remoteParticipants is a Map keyed by sid; the local participant is
  // not in it, so .size is the count of *other* participants. We render
  // the count in the header, then build a fresh <ul> with the local
  // viewer pinned on top (marked .self) followed by every remote.
  // textContent (not innerHTML) keeps identity strings as text only.
  function renderParts() {{
    const others = Array.from(room.remoteParticipants.values());
    partsHeadEl.textContent = `room: ${{room.name || '?'}} — ${{others.length}} other${{others.length === 1 ? '' : 's'}}`;
    partsListEl.replaceChildren();
    const localId = room.localParticipant && room.localParticipant.identity;
    if (localId) {{
      const selfLi = document.createElement('li');
      selfLi.className = 'self';
      selfLi.textContent = `${{localId}} (you)`;
      partsListEl.appendChild(selfLi);
    }}
    for (const p of others) {{
      const li = document.createElement('li');
      li.textContent = p.identity;
      partsListEl.appendChild(li);
    }}
  }}

  function attachVideoTrack(track) {{
    if (!track || attached || track.kind !== LivekitClient.Track.Kind.Video) return;
    track.attach(videoEl);
    // Tell the browser to minimize its WebRTC jitter buffer. Default
    // pre-roll is ~150-200ms in Chrome; on a stable LAN we'd rather
    // take the occasional jitter glitch than carry that latency.
    if (track.receiver) {{ track.receiver.playoutDelayHint = 0; }}
    attached = true;
    setState('connected', 'streaming: ' + (track.sid || 'video'));
  }}

  function subscribeAndAttachExistingVideo() {{
    for (const participant of room.remoteParticipants.values()) {{
      const publications = participant.videoTrackPublications || participant.trackPublications;
      for (const publication of publications.values()) {{
        if (publication.kind && publication.kind !== LivekitClient.Track.Kind.Video) continue;
        if (publication.track) {{
          attachVideoTrack(publication.track);
        }} else if (typeof publication.setSubscribed === 'function') {{
          publication.setSubscribed(true);
        }}
      }}
    }}
  }}

  function handleGpsData(payload, participant, topic) {{
    if (topic && topic !== 'phone-gps') return;
    try {{
      const text = new TextDecoder().decode(payload);
      const gps = JSON.parse(text);
      if (gps.type && gps.type !== 'phone_gps') return;
      const lat = Number(gps.lat).toFixed(6);
      const lon = Number(gps.lon).toFixed(6);
      const accuracy = Number(gps.accuracy_m).toFixed(1);
      const ageSec = Math.max(0, (Date.now() - Number(gps.timestamp_ms || 0)) / 1000).toFixed(1);
      const source = participant && participant.identity ? participant.identity : 'publisher';
      gpsEl.textContent = `GPS: ${{lat}}, ${{lon}}\\n±${{accuracy}} m · ${{ageSec}}s ago · ${{source}}`;
    }} catch (e) {{
      console.warn('failed to parse gps data', e);
    }}
  }}

  room.on(LivekitClient.RoomEvent.TrackSubscribed, (track) => {{
    attachVideoTrack(track);
  }});
  room.on(LivekitClient.RoomEvent.TrackPublished, (publication) => {{
    if (typeof publication.setSubscribed === 'function') publication.setSubscribed(true);
    subscribeAndAttachExistingVideo();
  }});
  room.on(LivekitClient.RoomEvent.ParticipantConnected, () => {{
    renderParts();
    subscribeAndAttachExistingVideo();
  }});
  room.on(LivekitClient.RoomEvent.ParticipantDisconnected, () => {{
    renderParts();
    attached = false;
    videoEl.removeAttribute('src');
    videoEl.load();
  }});
  room.on(LivekitClient.RoomEvent.DataReceived, handleGpsData);
  room.on(LivekitClient.RoomEvent.Disconnected, () => {{ setState('error', 'disconnected'); }});
  room.connect(LIVEKIT_URL, LIVEKIT_TOKEN)
    .then(() => {{
      if (!attached) setState('connected', 'connected, waiting for video…');
      renderParts();
      subscribeAndAttachExistingVideo();
    }})
    .catch(e => {{ setState('error', 'error: ' + e.message); }});
</script></body></html>
"""


def make_token(api_key: str, api_secret: str, room: str, identity: str) -> str:
    """Mint a viewer JWT: subscribe-only, scoped to one room.

    `can_publish=False` means even if a malicious page reused this token
    it couldn't push tracks; `can_subscribe=True` is what lets us see
    other participants. The token is signed with the shared API secret,
    so the LiveKit server validates it without any extra round-trip.
    """
    return (
        api.AccessToken(api_key, api_secret)
        .with_identity(identity)
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room,
                can_subscribe=True,
                can_publish_data=False,
                can_publish=False,
            )
        )
        .to_jwt()
    )


def make_publisher_token(api_key: str, api_secret: str, room: str, identity: str) -> str:
    """Mint a publish-only JWT for a camera publisher such as the Android app."""
    return (
        api.AccessToken(api_key, api_secret)
        .with_identity(identity)
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room,
                can_publish=True,
                can_publish_data=True,
                can_subscribe=False,
            )
        )
        .to_jwt()
    )


def main() -> None:
    """Parse args, mint the token, render the page, serve it, open the browser."""
    parser = argparse.ArgumentParser(
        description="Lean browser-based LiveKit viewer.",
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
    # --- Room / identity: matches the streamer's defaults so they meet up. ---
    parser.add_argument("--room", default="test-room", help="Room name to join")
    parser.add_argument(
        "--identity", default="viewer", help="Participant identity shown to other peers"
    )
    # --- Local web server that hosts the viewer page. ---
    parser.add_argument(
        "--port", type=int, default=8080, help="Local HTTP port for the viewer page"
    )
    parser.add_argument(
        "--bind",
        default="127.0.0.1",
        help="Interface to bind to. Defaults to loopback so the JWT-bearing "
        "page isn't exposed beyond this host. The Docker entrypoint "
        "overrides this to 0.0.0.0 so the published port is reachable; "
        "in that mode pin Docker's publish to host loopback "
        "(`-p 127.0.0.1:8080:8080`) unless you really mean to share.",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Don't auto-open the browser; just print the URL",
    )
    args = parser.parse_args()

    # Render once at startup — the page is static for this process's lifetime.
    token = make_token(args.api_key, args.api_secret, args.room, args.identity)
    html = HTML_TEMPLATE.format(url=args.url, token=token, room=args.room).encode(
        "utf-8"
    )

    class Handler(http.server.BaseHTTPRequestHandler):
        """Serves the viewer page and a tiny dev token endpoint."""

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/token":
                query = parse_qs(parsed.query)
                room = query.get("room", [args.room])[0]
                identity = query.get("identity", ["android-oakley"])[0]
                publisher_token = make_publisher_token(
                    args.api_key,
                    args.api_secret,
                    room,
                    identity,
                )
                body = json.dumps(
                    {
                        "url": args.url,
                        "room": room,
                        "identity": identity,
                        "token": publisher_token,
                    }
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            # Token is embedded in the HTML; don't let a stale page sit in cache.
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(html)

        def log_message(self, format, *args):
            # Silence default per-request stderr access logs.
            pass

    # See --bind help: the page contains a signed JWT, so the default
    # is loopback. Container runs override to 0.0.0.0 and the user is
    # expected to publish with `-p 127.0.0.1:8080:8080`.
    with socketserver.TCPServer((args.bind, args.port), Handler) as srv:
        # When bound to 0.0.0.0, "localhost" is what the host user types.
        display_host = "localhost" if args.bind == "0.0.0.0" else args.bind
        local = f"http://{display_host}:{args.port}/"
        print(f"viewer ready: {local}  (room={args.room}, livekit={args.url})")
        if not args.no_open:
            # webbrowser.open can block (e.g. spawning a new window) —
            # push it off-thread so the HTTP server starts serving immediately.
            threading.Thread(target=lambda: webbrowser.open(local), daemon=True).start()
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print()


if __name__ == "__main__":
    main()
