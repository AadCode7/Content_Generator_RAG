# Live Stream Trend Detector and Automatic Clip Generator

## Objective

Build a local-first pipeline that monitors an authorised creator's Twitch chat, detects unusual message-rate bursts, records an authorised live media input, extracts a configurable clip around each spike, and transcribes candidate clips. It complements the existing GTA VI research and script-generation workflow; it does not replace it.

## Architecture

1. **Source setup**: choose a Twitch channel and separately provide a direct media URL that you own or have explicit permission to record. The application does not resolve Twitch channel pages or retrieve protected VODs.
2. **Chat ingestion**: Twitch IRC WebSocket with a user OAuth token carrying the `chat:read` scope. IRC is used for the first MVP; EventSub is the preferred future integration for richer event handling.
3. **Recording**: FFmpeg writes short MPEG-TS segments and a CSV media-timeline index. This avoids seeking into an unfinished MP4 file.
4. **Trend detection**: Python counts messages in 10-second buckets and compares each bucket with the preceding 10 minutes using a median/MAD baseline. Minimum-count, ratio and cooldown controls reduce false positives.
5. **Clip extraction**: after the post-roll is available, FFmpeg concatenates the relevant segments and writes a 30-second MP4 by default (15 seconds before and 15 seconds after the detected event).
6. **Transcription**: optional faster-whisper creates JSON word-level timestamps. The default model is `tiny` on CPU to keep the workload manageable.
7. **Review**: candidate clips and JSON sidecars are saved to `data/live_clips`. A later dashboard phase can show chat rate, transcript, preview, title suggestions and approval state.

## Twitch live-stream option for channels that enable Clips

For public Twitch channels where the broadcaster has enabled viewer clipping, a future adapter can use Twitch's official Create Clip API instead of extracting the full media stream:

- The viewer's user access token needs the `clips:edit` scope.
- The broadcaster must have Clips enabled and must not have blocked the viewer through follower/subscriber-only or other clip restrictions.
- The API captures up to 90 seconds around the request and provides an edit URL. By default it publishes up to the last 30 seconds of that capture window.
- Because Twitch's documented capture window is approximately 85 seconds before and 5 seconds after the request, calling the endpoint roughly 10 seconds after a detected chat spike can place the default 30-second clip approximately 15 seconds before and after the spike. Network and platform timing make this approximate, so it must be calibrated.
- The Twitch-hosted clip can be reviewed through its returned URL/edit URL. Downloading the media for local Whisper transcription is a separate permission: the Clips Download API requires `editor:manage:clips` or `channel:manage:clips` and the corresponding broadcaster/editor authorisation.
- For an offline VOD, Twitch's Create Clip From VOD endpoint is restricted to the broadcaster or an authorised editor.

This adapter is not yet implemented in the current CLI. It is the recommended next step for monitoring creator channels without requiring a direct HLS/media URL. The current FFmpeg mode remains for media inputs you are authorised to record locally.

Streamlink is a free, open-source stream extractor with a Twitch plugin, but it is not included as a default downloader. Use it only where recording is expressly permitted and consistent with Twitch's terms; a public player URL is not itself permission to download or republish the stream.

## Current implementation

- Twitch IRC read-only client with reconnect handling and PING/PONG support.
- Pure Python chat spike detector with configurable thresholds and cooldown.
- FFmpeg segment recorder and clip extraction using the segment CSV timeline.
- CLI runner and optional faster-whisper transcription script.
- Offline tests for spike scoring and IRC message parsing.

## Setup

### 1. Install system tools

- Python 3.11 recommended.
- FFmpeg installed and available on PATH (`ffmpeg -version`).
- Docker is not required for this MVP.
- For transcription, install the optional package extra only when needed.

### 2. Install Python packages

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install --no-deps -e .
```

### 3. Configure credentials and authorised video source

Copy `.env.example` to `.env` and set:

- `TWITCH_USERNAME`: your Twitch account username.
- `TWITCH_OAUTH_TOKEN`: user OAuth token with `chat:read`. Treat it like a password.
- `LIVE_VIDEO_URL`: direct media input you own or have explicit permission to record. Do not put credentials in Git or share them in chat.

The token is used only for chat reading. The video input is passed to FFmpeg. This MVP intentionally does not scrape creator pages, bypass login/DRM, or download third-party VODs.

### 4. Start the live clipper

```powershell
python scripts/run_live_clipper.py --channel YOUR_CHANNEL --confirm-rights
```

Stop with Ctrl+C. Clips, metadata JSON and FFmpeg logs are saved under `data/live_clips` by default.

Tune thresholds for each channel:

```powershell
python scripts/run_live_clipper.py --channel YOUR_CHANNEL --confirm-rights --min-messages 10 --ratio-threshold 3 --cooldown-seconds 60
```

The pre-roll and post-roll must sum to the clip duration. The default is 15 + 15 = 30 seconds. The `--sync-offset-seconds` option compensates for measured delay between chat timestamps and the media input.

### 5. Transcribe candidate clips

```powershell
python -m pip install -e ".[transcription]"
python scripts/transcribe_clips.py data/live_clips --model tiny --device cpu
```

The script writes one `.transcript.json` file per clip. Use `base` or `small` for better accuracy if the CPU and RAM budget allows it. CUDA is optional and requires a compatible CUDA/cuDNN environment.

## Detection logic

For each 10-second bucket, calculate:

- current message count
- median count across the previous 60 buckets (10 minutes)
- median absolute deviation (MAD)
- activity ratio against the median

A spike is emitted when the current count reaches the maximum of:
- configured minimum message count
- baseline median multiplied by the ratio threshold
- baseline median plus the MAD multiplier times the MAD (with a small floor)

A cooldown prevents repeated clips from the same burst. This is a heuristic, not a claim that a moment is objectively viral. Tune it with real channel traffic.

## Important limitations

- Chat and video clocks are not perfectly aligned. Measure the delay and set `--sync-offset-seconds`; validate against a test recording before unattended use.
- This MVP records one authorised media input and monitors one Twitch chat channel per process.
- Twitch IRC is a basic first implementation. EventSub, OAuth refresh, chat deduplication, multi-channel scheduling and persistent job state are follow-up work.
- A direct media URL may expire or require headers/cookies. Do not paste private credentials into command-line arguments or commit them.
- The local recorder needs disk space. Stop it when not in use and periodically archive/delete old segments and clips.
- The current Streamlit app is not a process supervisor. Run this long-lived capture worker locally, not on Streamlit Community Cloud or a short-lived serverless function.
- The first release saves candidates locally. It does not auto-publish or generate claims about creator consent.

## Development phases

### Phase 1 — implemented in this repository
Chat listener, spike detector, segmented FFmpeg recorder, clip extraction, optional Whisper transcription, CLI and offline tests.

### Phase 2 — reliability and Twitch-native clips
Add the official Twitch Create Clip API adapter for channels that allow viewer clipping, handle OAuth scopes and clip polling, and download media only when the viewer is an authorised broadcaster/editor. Move chat to EventSub where appropriate, refresh OAuth tokens safely, improve reconnect and duplicate-event handling, monitor recorder health, add disk quotas, and calibrate chat/video clock drift.

### Phase 3 — candidate ranking
Combine chat spike strength, unique chatter count, transcript excitement/context, scene changes and audio peaks. Add a manual approval queue; do not auto-publish.

### Phase 4 — dashboard integration
Add a Live Clips page to Streamlit with stream configuration, live chat-rate chart, spike timeline, clip preview, transcript, title/hook generation via the existing Groq service, and approve/reject/export actions.

### Phase 5 — optional portrait output
Use FFmpeg crop/scale filters or OpenShorts for 9:16 reframing and subtitle burn-in. Keep this optional so the core pipeline stays lightweight.
