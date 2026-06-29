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
4. On first launch the app opens your browser to a **Settings** page.
5. **Configure your channels in the form:**
   - **Twitch channel** — the bit after `twitch.tv/` (no `#`)
   - **TikTok handle** — include the `@`
   - **Advanced → EulerStream API key** — optional, for higher TikTok rate limits
   - Click **Save & connect**. The app reconnects to the new channels
     instantly — no restart needed.
6. Click **Open overlay** (or the gear icon top-right) to see the merged feed.
7. **Add it to OBS:** Sources → `+` → Browser →
   URL: `http://localhost:8000/?bg=transparent&showsource=1`. Width 600, height
   800 is a good start. The background is transparent so it overlays cleanly
   on your stream. Use the **Copy OBS URL** button on the settings page if you
   change ports.

Your settings are persisted to `settings.json` next to the binary, so they
stick across launches. A log file `live-chat-agg.log` is also created next to
the binary (it'll show why TikTok said "not live, retrying" etc.).

> If the binary can't write next to itself (e.g. you dragged it to
> `/Applications`), `settings.json` and the log are placed in
> `~/.live-chat-agg/` instead.

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

## Configuration

There are two layers, in order of precedence:

1. **In-app settings** (`settings.json`, edited via the **Settings** page at
   <http://localhost:8000/settings>) — for streamer-facing config that needs to
   change between sessions. Persists `twitch_channel`, `tiktok_username`,
   `sign_api_key`. Changes apply live without restarting the process.
2. **`.env`** — for power-user / dev defaults. Everything below is supported.

| Var | Required | Notes |
|---|---|---|
| `TWITCH_CHANNEL` | for Twitch | Channel login name, no `#`. Overridable via `/settings`. |
| `TWITCH_OAUTH_TOKEN` | no | Reading works anonymously without it. |
| `TIKTOK_USERNAME` | for TikTok | The `@handle` to follow when live. Overridable via `/settings`. |
| `SIGN_API_KEY` | no | EulerStream key for TikTokLive signing — see below. Overridable via `/settings`. |
| `HOST` | no | Default `0.0.0.0` (`127.0.0.1` in the packaged binary). |
| `PORT` | no | Default `8000`. |
| `RING_BUFFER_SIZE` | no | Backfill size for new overlays. Default `50`. |

If neither `TWITCH_CHANNEL` nor `TIKTOK_USERNAME` is set (in either layer) and
no `settings.json` exists yet, the root URL redirects to `/settings` on
first launch and a built-in fake publisher runs in the background.

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
  settings_store.py    settings.json atomic read/write + live-reload layering
  server.py            FastAPI: /ws, /settings, /api/settings, /api/reconnect
  main.py              dev entrypoint (uvicorn from cwd .env)
  launcher.py          packaged-binary entrypoint (.env-next-to-binary + auto-browser)
  connectors/
    base.py            Connector ABC
    twitch.py          anonymous IRC-over-WS reader + IRCv3 tag parser
    tiktok.py          TikTokLive wrapper with offline/reconnect handling
static/
  index.html / overlay.js / overlay.css   the OBS-friendly overlay
  settings.html / settings.css / settings.js   the in-app config form
run_packaged.py        PyInstaller entry script (imports app.launcher.main)
live_chat_agg.spec     PyInstaller spec: onedir+.app on macOS, onefile .exe elsewhere
.github/workflows/release.yml   matrix build (mac+win), auto-publish on tag push
```

## Releasing binaries

GitHub Actions builds Mac `.app` and Windows `.exe` artifacts and attaches them
to a Release whenever you push a tag matching `v*`:

```bash
git tag v0.2.0
git push origin v0.2.0
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
