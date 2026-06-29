# Live Chat Aggregator (Twitch + TikTok)

A self-hosted app that merges **Twitch** and **TikTok** live chat into a single
real-time feed. The feed is served over a WebSocket and rendered by a browser
overlay that doubles as an **OBS browser source** (transparent background by
default).

All connection, parsing, normalization, and serving logic runs in one Python
`asyncio` process. The only non-Python artifact is a thin static HTML/JS overlay.

## How it works

```
TwitchConnector (IRC-over-WS)  ─┐
                                ├─► EventBus (broadcast + ring buffer) ─► FastAPI /ws ─► Browser overlay / OBS
TikTokConnector (TikTokLive)   ─┘
```

Each connector runs as an independently supervised task that auto-reconnects
with jittered exponential backoff. Connectors push a normalized `ChatMessage`
onto the `EventBus`, which fans out to every connected overlay and keeps a small
ring buffer so a freshly-opened overlay backfills the last N messages.

## ⚠️ Important caveat: Twitch is official, TikTok is not

| Platform | Access | Stability |
|---|---|---|
| **Twitch** | Official anonymous IRC read API. No OAuth needed for reading. | Rock-solid. Stable for a decade. |
| **TikTok** | **Reverse-engineered.** Reads the internal Webcast push service via the [`TikTokLive`](https://pypi.org/project/TikTokLive/) library, which depends on a third-party signing service (EulerStream). | **Fragile.** Will break periodically when TikTok changes things. |

The TikTok connector is isolated by design: any TikTok failure (streamer
offline, signing/rate-limit errors, library breakage) only triggers a backoff +
retry on that one task. It never affects Twitch or the web server.

"Streamer not live" is the *normal* state most of the time — the app logs
`not live, retrying` and backs off rather than crashing or spamming errors.

## Requirements

- Python 3.11+ (developed/tested on 3.14)
- A Twitch channel name and/or a TikTok `@handle`

## Setup

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                 # then fill in the values below
python -m app.main
```

Open <http://localhost:8000> to see the overlay.

## Configuration (`.env`)

| Var | Required | Notes |
|---|---|---|
| `TWITCH_CHANNEL` | for Twitch | Channel login name, no `#`. |
| `TWITCH_OAUTH_TOKEN` | no | Reading works anonymously without it. |
| `TIKTOK_USERNAME` | for TikTok | The `@handle` to follow when live. |
| `SIGN_API_KEY` | no | EulerStream API key for TikTokLive signing — see below. |
| `HOST` | no | Default `0.0.0.0`. |
| `PORT` | no | Default `8000`. |
| `RING_BUFFER_SIZE` | no | Backfill size for new overlays. Default `50`. |

If neither `TWITCH_CHANNEL` nor `TIKTOK_USERNAME` is set, a built-in fake
publisher streams demo messages every 2s so you can verify the overlay works.

### `SIGN_API_KEY` (optional)

TikTok WebSocket connections require a signed handshake provided by EulerStream.
Without a key you share a public rate limit and may hit throttling. Provide a
[EulerStream](https://www.eulerstream.com/) API key via `SIGN_API_KEY` to raise
your limits. It is applied automatically when present.

## OBS browser source

Add a **Browser Source** in OBS pointing at:

```
http://localhost:8000/?bg=transparent&showsource=1
```

The overlay renders with a transparent background by default, with text shadows
for legibility over arbitrary video.

### Overlay query parameters

| Param | Values | Default | Effect |
|---|---|---|---|
| `bg` | `transparent`, `dark`, `light` | `transparent` | Background mode. |
| `limit` | integer | `100` | Max rendered rows. |
| `showsource` | `1` | off | Show the platform icon / avatar. |
| `fontsize` | integer (px) | `18` | Message font size. |

Twitch is accented purple (`#9146FF`); TikTok teal (`#25F4EE`). Twitch supplies
per-user colors directly; TikTok colors are derived deterministically from the
user id (hash → HSL) so each user keeps a consistent color.

## Project layout

```
app/
  config.py            pydantic-settings config from .env
  models.py            ChatMessage contract + deterministic color helper
  bus.py               EventBus: broadcast + ring buffer
  supervisor.py        run-forever-with-backoff wrapper
  server.py            FastAPI: /ws, static mount, lifespan, connector wiring
  main.py              entrypoint
  connectors/
    base.py            Connector ABC
    twitch.py          anonymous IRC-over-WS reader + IRCv3 tag parser
    tiktok.py          TikTokLive wrapper with offline/reconnect handling
static/
  index.html / overlay.js / overlay.css   the OBS-friendly overlay
```
