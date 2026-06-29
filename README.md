# Live Chat Aggregator (Twitch + TikTok)

A self-hosted app that merges **Twitch** and **TikTok** live chat into a single
real-time feed. The feed is served over a WebSocket and rendered by a browser
overlay that doubles as an **OBS browser source** (transparent background by
default).

All connection, parsing, normalization, and serving logic runs in one Python
`asyncio` process. The only non-Python artifact is a thin static HTML/JS overlay.

## Features

- **Unified chat** — Twitch and TikTok messages in one feed. Twitch nicks are
  accented purple (`#7B68EE`), TikTok nicks blue (`#6495ED`), on a dark
  semi-transparent card; message text is white.
- **Live stats header** — a two-column counter strip: **TikTok** (viewers,
  gifts, subscriptions this stream, likes) and **Twitch** (viewers,
  subscriptions this stream).
- **Gifts panel** — TikTok gifts with name, image, and giver; identical gifts
  from the same user **stack** (`×N`).
- **Subscriptions inline** — subs appear in the chat flow, de-emphasized.
- **Operator controls** (visible only outside OBS source mode):
  - **Block** a message author with one click.
  - **Show on stream** — pin any message so all overlays (and OBS) display it.
  - **Composer** — send a message to Twitch *or* TikTok chat, with a remembered
    platform choice, quick-insert **templates** (managed in Settings), and a
    built-in **emoji** picker.
- **Text-to-speech** — optionally read each chat message aloud in **Russian**
  (the nickname is never read). Latin-script messages are also read with a
  Russian voice. Two engines: **browser** (offline OS voices) or **neural**
  (edge-tts online voices, more natural). Auditioned and chosen in Settings.
- **Test messages** — a config flag and a composer **Test** button let you inject
  demo chat lines before a real stream is connected. Off by default.
- **Desktop overlay mode** — an always-on-top, transparent, click-through window
  that floats over your other apps (PySide6/Qt). See *Desktop overlay mode* below.

> Sending messages and Twitch viewer/sub counts require extra credentials. See
> *Configuration* and the security warnings there before enabling them.

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
   change between sessions. Persists all the runtime keys below (channels,
   credentials, TTS, templates). Changes apply live without restarting the
   process.
2. **`.env`** — for power-user / dev defaults. Everything below is supported.

| Var | Required | Notes |
|---|---|---|
| `TWITCH_CHANNEL` | for Twitch | Channel login name, no `#`. Overridable via `/settings`. |
| `TWITCH_OAUTH_TOKEN` | to **send** to Twitch | OAuth token with the `chat:edit` scope. Reading works anonymously without it. |
| `TWITCH_BOT_USERNAME` | to **send** to Twitch | Login name the OAuth token belongs to. Both this and the token are required to send. |
| `TWITCH_CLIENT_ID` | for Twitch counts | Twitch app Client ID, for live viewer/sub counts via the Helix API. |
| `TWITCH_CLIENT_SECRET` | for Twitch counts | Paired with the Client ID. Stored locally only. |
| `TIKTOK_USERNAME` | for TikTok | The `@handle` to follow when live. Overridable via `/settings`. |
| `SIGN_API_KEY` | no | EulerStream key for TikTokLive signing — see below. Overridable via `/settings`. |
| `TIKTOK_SESSIONID` | to **send** to TikTok | ⚠️ Your TikTok session cookie — **grants full access to your account**. Local only; never share it. See the warning below. |
| `TIKTOK_TARGET_IDC` | no | TikTok data-center hint (e.g. `useast1a`). Only needed if sending fails with a region error. |
| `TTS_ENABLED` | no | `true`/`false`. Read chat aloud (Russian). Default `false`. |
| `TTS_ENGINE` | no | `browser` (OS voices, offline) or `neural` (edge-tts, online). Default `browser`. |
| `TTS_VOICE` | no | Preferred **browser** voice name. Blank = first available Russian voice. |
| `TTS_NEURAL_VOICE` | no | edge-tts voice for the neural engine. Default `ru-RU-SvetlanaNeural`. |
| `TTS_FALLBACK_TO_BROWSER` | no | `true`/`false`. If neural synthesis fails, speak with a browser voice. Default `false`. |
| `TEMPLATES` | no | JSON array of quick-reply phrases for the composer. |
| `ENABLE_TEST_MESSAGES` | no | `true`/`false`. Emit fake demo chat when no stream is connected. Default `false`. |
| `HOST` | no | Default `0.0.0.0` (`127.0.0.1` in the packaged binary). |
| `PORT` | no | Default `8000`. |
| `RING_BUFFER_SIZE` | no | Backfill size for new overlays. Default `50`. |

If neither `TWITCH_CHANNEL` nor `TIKTOK_USERNAME` is set (in either layer) and
no `settings.json` exists yet, the root URL redirects to `/settings` on first
launch. Demo/test messages are **off by default** — set `ENABLE_TEST_MESSAGES`
(or tick the box in Settings) to have the overlay emit fake chat lines while no
stream is connected, useful for styling before going live. You can also inject a
one-off line with the composer's **Test** button (operator view only).

### ⚠️ Security: sending credentials

Reading chat needs **no** credentials. Sending and counts do, and they are
sensitive:

- **TikTok `TIKTOK_SESSIONID`** is your logged-in session cookie. Anyone who has
  it can act as **your full TikTok account**. It is stored only in the local
  `settings.json`/`.env` on your machine and is never transmitted anywhere except
  to TikTok itself when sending. Do not commit it, screen-share it, or paste it
  anywhere public. Leave it blank unless you actually want to send to TikTok chat.
- **Twitch `TWITCH_OAUTH_TOKEN`** must have the `chat:edit` scope and belongs to
  the account named in `TWITCH_BOT_USERNAME`. Treat it like a password. Reading
  never needs it.

### Text-to-speech setup

TTS reads the **message text** aloud (never the nickname). Enable **Read chat
aloud** in Settings, choose an engine, and use the **Preview** button to audition
voices before picking one. There are two engines:

**Browser** (`TTS_ENGINE=browser`) — uses your operating system's voices through
the overlay's browser. Offline and instant, but you need a Russian system voice
installed:

- **macOS**: System Settings → Accessibility → Spoken Content → System Voice →
  Manage Voices → add a Russian voice (e.g. **Milena**).
- **Windows**: Settings → Time & Language → Speech → add a Russian voice
  (e.g. **Microsoft Irina** or **Pavel**).

**Neural** (`TTS_ENGINE=neural`) — uses [edge-tts](https://github.com/rany2/edge-tts)
Microsoft online neural voices. Much more natural, but needs an internet
connection (~2-3s latency). Good Russian voices: **`ru-RU-SvetlanaNeural`**
(female) and **`ru-RU-DmitryNeural`** (male). edge-tts is bundled in the released
binaries; from source run `pip install edge-tts`. Set `TTS_FALLBACK_TO_BROWSER`
to fall back to a browser voice if neural synthesis fails (e.g. offline).

Latin-script text is still spoken with a Russian voice in both engines.

> **OBS double-audio:** if you keep an operator window open *and* add the overlay
> as an OBS browser source, both will speak each line. Append `?mute_tts=1` to the
> OBS source URL so only the operator window speaks.

### Chat templates

Saved quick-reply phrases for the composer. Add/remove them on the Settings page
(or via the `TEMPLATES` JSON array). They appear in the composer's templates
popup for one-click insertion when sending.

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
| `mute_tts` | `1` | off | Disable all TTS in this window (use on the OBS source to avoid double audio). |

Twitch is accented purple (`#7B68EE`); TikTok blue (`#6495ED`). Twitch supplies
per-user colors directly; TikTok colors are derived deterministically from the
user id (hash → HSL) so each user keeps a consistent color.

The operator composer, per-message **Block** / **Show on stream** buttons, the
stats header, and the gifts panel are part of the normal overlay. The
moderation controls and composer are **hidden in OBS source mode**
(`?bg=transparent&showsource=1`) so they never appear on stream.

## Desktop overlay mode

In addition to the browser/OBS overlay, the app can open an **always-on-top,
transparent, click-through** window that floats over your other applications —
handy for monitoring chat while you do something else on the same screen.

Enable it with either a CLI flag or an environment variable:

```bash
# from source
python -m app.launcher --desktop
# or
LCA_DESKTOP=1 python -m app.launcher
```

The packaged binaries also accept the `--desktop` flag / `LCA_DESKTOP=1`.

Desktop mode uses [PySide6](https://pypi.org/project/PySide6/) (Qt WebEngine). It
is bundled into the released binaries. If you run from source and PySide6 isn't
installed, the app logs a warning and falls back to the normal browser flow —
install it with `pip install PySide6`. The window is click-through, so it won't
intercept your mouse; close it (or Ctrl-C the console) to stop.

## Project layout

```
app/
  config.py            pydantic-settings config from .env
  models.py            wire frames (chat/sub/gift/stats) + deterministic color helper
  bus.py               EventBus: broadcast + ring buffer + blocklist
  stats.py             StatsState: debounced live counters (viewers/gifts/subs/likes)
  supervisor.py        run-forever-with-backoff wrapper
  settings_store.py    settings.json atomic read/write + live-reload layering
  server.py            FastAPI: /ws, /settings, /api/{settings,reconnect,send,block,pin}
  main.py              dev entrypoint (uvicorn from cwd .env)
  launcher.py          packaged-binary entrypoint (+ --desktop overlay mode)
  desktop.py           PySide6 always-on-top transparent click-through window
  connectors/
    base.py            Connector ABC (read + optional send)
    twitch.py          anonymous IRC-over-WS reader + IRCv3 parser + subs + send
    twitch_helix.py    Helix poller for live viewer counts
    tiktok.py          TikTokLive wrapper: chat/gifts/likes/follows/subs + send
static/
  index.html / overlay.js / overlay.css   the OBS-friendly overlay + composer
  tts.js                                   Russian text-to-speech helper
  settings.html / settings.css / settings.js   the in-app config form
run_packaged.py        PyInstaller entry script (imports app.launcher.main)
live_chat_agg.spec     PyInstaller spec: onedir+.app on macOS, onefile .exe elsewhere
.github/workflows/release.yml   matrix build (mac+win), auto-publish on tag push
```

## Releasing binaries

GitHub Actions builds Mac `.app` and Windows `.exe` artifacts and attaches them
to a Release whenever you push a tag matching `v*`:

```bash
git tag v3.0.0
git push origin v3.0.0
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
