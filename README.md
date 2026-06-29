# Live Chat Aggregator (Twitch + TikTok)

A self-hosted app that merges **Twitch** and **TikTok** live chat into a single
real-time feed. The feed is served over a WebSocket and rendered by a browser
overlay that doubles as an **OBS browser source** (transparent background by
default).

All connection, parsing, normalization, and serving logic runs in one Python
`asyncio` process. The only non-Python artifact is a thin static HTML/JS overlay.

## Quick install (no Python required)

Pre-built binaries are published with each release. **No Python install needed.**

1. Go to the **[Releases](../../releases/latest)** page and download:
   - **macOS** (Apple Silicon): `live-chat-agg-macos-arm64.zip`
   - **Windows** (x64): `live-chat-agg-windows-x64.zip`
2. Unzip it anywhere convenient (Desktop, `~/Applications`, etc.).
3. **Launch:**
   - **macOS**: double-click `live-chat-agg.app`. The first time you run it,
     macOS will block it because the app isn't notarized. Fix it once:
     **right-click the app → Open → Open** in the dialog. After that,
     normal double-click works.
   - **Windows**: double-click `live-chat-agg.exe`. Windows SmartScreen will
     warn that the publisher is unverified. Click **More info → Run anyway**.
4. On first launch the app creates a `.env` file next to the binary and opens
   your browser to <http://localhost:8000>. You'll see a built-in demo stream.
5. **Configure your channels:** open the freshly-created `.env` in a text
   editor, fill in `TWITCH_CHANNEL` and/or `TIKTOK_USERNAME`, save, and
   relaunch the app.
6. **Add it to OBS:** Sources → `+` → Browser →
   URL: `http://localhost:8000/?bg=transparent&showsource=1`. Width 600, height
   800 is a good start. The background is transparent so it overlays cleanly
   on your stream.

A log file `live-chat-agg.log` is created next to the binary for
troubleshooting (it'll show why TikTok said "not live, retrying" etc.).

> If the binary can't write next to itself (e.g. you dragged it to
> `/Applications`), the `.env` and log are placed in `~/.live-chat-agg/`
> instead.

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

## Build from source

Use this path if you want to hack on the code, run on Linux, or build your own
Mac/Windows binary.

**Requirements:** Python 3.11+ (developed/tested on 3.14) and a Twitch channel
name and/or a TikTok `@handle`.

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
  main.py              dev entrypoint (uvicorn from cwd .env)
  launcher.py          packaged-binary entrypoint (.env-next-to-binary + auto-browser)
  connectors/
    base.py            Connector ABC
    twitch.py          anonymous IRC-over-WS reader + IRCv3 tag parser
    tiktok.py          TikTokLive wrapper with offline/reconnect handling
static/
  index.html / overlay.js / overlay.css   the OBS-friendly overlay
run_packaged.py        PyInstaller entry script (imports app.launcher.main)
live_chat_agg.spec     PyInstaller spec: onedir+.app on macOS, onefile .exe elsewhere
.github/workflows/release.yml   matrix build (mac+win), auto-publish on tag push
```

## Releasing binaries

GitHub Actions builds Mac `.app` and Windows `.exe` artifacts and attaches them
to a Release whenever you push a tag matching `v*`:

```bash
git tag v0.1.0
git push origin v0.1.0
```

You can also trigger a dry-run build (no Release published) via the
**Actions → release → Run workflow** button on GitHub.

To build locally:

```bash
pip install -r requirements-dev.txt
pyinstaller live_chat_agg.spec --noconfirm --clean
# macOS  → dist/live-chat-agg.app
# Windows / Linux → dist/live-chat-agg.exe (or live-chat-agg)
```
