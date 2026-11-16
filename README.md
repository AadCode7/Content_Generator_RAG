# GTA VI News Researcher

A lightweight cloud-AI research dashboard that collects GTA VI news and webpage content, uses Groq to identify interesting discoveries, and turns them into short-form video ideas and voiceover scripts.

The app runs on your laptop without local LLM inference. Text analysis and script generation happen through the Groq API.

## Features

- Collect GTA VI-related articles from RSS feeds and configured webpages.
- Extract readable article text with Trafilatura and BeautifulSoup.
- Store sources, article content and discoveries in SQLite.
- Use Groq to extract up to three content ideas per article.
- Score ideas for novelty, shareability and visual potential.
- Generate hooks, 20-35 second voiceover drafts, visual notes and hashtags.
- Approve/reject ideas, edit scripts and download production-ready text files.
- Add, enable and disable sources.
- Keep the originating source URL attached to every idea.
- Detect authorised Twitch chat activity spikes and automatically extract candidate clips from an authorised live media input.
- Optionally transcribe candidate clips with faster-whisper.
- Review generated clips in the Streamlit Live Clips tab with video previews, chat-spike metrics, transcripts, downloads and persistent approve/reject status.
- Generate clip-specific editing packages inside the preview: hooks, timed on-screen text, post captions, hashtags, mention/credit guidance, thumbnail concepts, editing timelines, audio guidance and CTAs. Groq personalises suggestions from the transcript and clip metadata; local starter suggestions work without an API key.

This first version does not independently verify claims and does not run cross-source duplicate-story detection. Review source material before publishing.

## Project structure

    Content_Generator_RAG/
    ├── app.py
    ├── .env.example
    ├── .gitignore
    ├── pyproject.toml
    ├── requirements.txt
    ├── README.md
    ├── docs/
    │   ├── LIVE_CLIPPER_PLAN.md
    │   └── RIGHTS_AND_PLATFORM_COMPLIANCE.md
    ├── scripts/
    │   ├── run_live_clipper.py
    │   └── transcribe_clips.py
    ├── .streamlit/
    ├── src/gta_researcher/
    │   ├── live_clips.py
    │   └── twitch_chat.py
    └── tests/
        ├── test_live_clips.py
        └── test_twitch_chat.py

## Requirements

- Python 3.10 or later (Python 3.11 recommended).
- A Groq API key from https://console.groq.com/keys for the research dashboard.
- FFmpeg installed and available on PATH for live recording and clip extraction.
- Twitch username and a user OAuth token with the `chat:read` scope for the live chat reader.
- An authorised direct media URL for the video input.

No NVIDIA GPU is required for the research dashboard or the initial clipper. faster-whisper transcription is optional and runs on CPU by default.

## Setup on Windows

Open PowerShell in the project directory.

### 1. Create and activate a virtual environment

    py -3.11 -m venv .venv
    .\.venv\Scripts\Activate.ps1

If PowerShell blocks activation, use the virtual environment Python directly:

    .\.venv\Scripts\python.exe -m pip install --upgrade pip

### 2. Install dependencies

    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    python -m pip install --no-deps -e .

### 3. Configure Groq

Copy the example configuration:

    Copy-Item .env.example .env

Open .env and add your key:

    GROQ_API_KEY=your_groq_api_key
    GROQ_MODEL=openai/gpt-oss-20b

Keep .env private. It is excluded from Git.

The configured model must be available to your Groq account. Change GROQ_MODEL in .env or in the application sidebar if needed.

### 4. Start the application

    python -m streamlit run app.py

Streamlit prints a local URL, normally http://localhost:8501.

## Live chat-spike clipper

The live clipper is a separate local worker. Do not run it inside Streamlit Community Cloud or a short-lived serverless function.

1. Install FFmpeg and confirm `ffmpeg -version` works.
2. Add `TWITCH_USERNAME` and `TWITCH_OAUTH_TOKEN` to your local `.env`. The token must have `chat:read`; never commit it or share it.
3. Set `LIVE_VIDEO_URL` to a direct media input that you own or have explicit permission to record. This MVP does not resolve Twitch channel pages or download third-party VODs.
4. Start the worker:

       python scripts/run_live_clipper.py --channel YOUR_CHANNEL --confirm-rights

It records the authorised media source into short MPEG-TS segments, reads Twitch chat, detects message-rate spikes and saves a 30-second MP4 candidate around each spike. Defaults are 15 seconds before and 15 seconds after the event. Clips and JSON metadata are saved in `data/live_clips`.

Tune the detector with `--min-messages`, `--ratio-threshold` and `--cooldown-seconds`. If chat and video timestamps are offset, measure the delay and set `--sync-offset-seconds`.

See [the live clipper implementation plan](docs/LIVE_CLIPPER_PLAN.md) and [platform/rights notes](docs/RIGHTS_AND_PLATFORM_COMPLIANCE.md) before recording or publishing.

### Optional Whisper transcription

Install the optional dependency only when you want transcription:

    python -m pip install -e ".[transcription]"
    python scripts/transcribe_clips.py data/live_clips --model tiny --device cpu

The default `tiny` model is intended to keep CPU and memory use modest. Larger models may improve accuracy but take more memory and time.

## How to use the research dashboard

1. Enter your Groq API key in the sidebar or configure it in .env.
2. Test the Groq connection.
3. Open Sources and enable the sources you want to scan.
4. Add other RSS feeds or webpages when needed.
5. Open Research dashboard and run a scan.
6. Groq analyses collected article content and creates discoveries.
7. Open Discoveries to read ideas, edit hooks/scripts, regenerate scripts and approve useful ideas.
8. Open Production queue to download approved voiceover scripts and mark completed ideas as used.
9. Open Live Clips to preview candidate MP4s, inspect chat-spike statistics and transcripts, download files, and approve or reject candidates.
10. In the selected clip's Video editing assistant, choose the video type, platform and tone, then generate the editing package. Review and edit the hook/caption/hashtags, copy the thumbnail and timeline guidance, and download the complete Markdown editing brief. The package is saved beside the clip as a `.editor.json` sidecar.

The default sources are starting points. A source may return an error, change its feed URL, block automated requests or publish content that does not mention GTA VI in the title or summary. Add or disable sources as needed.

## Groq model configuration

The default model is openai/gpt-oss-20b. If it is unavailable to your account, select another model ID listed by the Groq API and update GROQ_MODEL.

The app calls Groq Chat Completions. Article text is sent to Groq for analysis, so do not add private or restricted material as a source.

## Storage

SQLite is stored at:

    data/gta_researcher.db

The data directory and database are ignored by Git. Back up this file if you want to preserve research between machines.

## Deploying on Streamlit Community Cloud

1. Push this repository to GitHub.
2. Create a new app at https://share.streamlit.io/.
3. Set the main file path to app.py.
4. In the app's Settings → Secrets, add:

       GROQ_API_KEY = "your_groq_api_key"
       GROQ_MODEL = "openai/gpt-oss-20b"

The app uses a local SQLite database by default. Some cloud environments have ephemeral local storage, so use a persistent database service before relying on cloud deployment for long-term storage. Run the live capture worker separately on a machine that remains online and has FFmpeg installed.

## Tests

Run:

    python -m unittest discover -s tests -v

The tests do not call Groq, Twitch or external media sources.
