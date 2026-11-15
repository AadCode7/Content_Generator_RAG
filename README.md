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

This first version does not independently verify claims and does not run cross-source duplicate-story detection. Review source material before publishing.

## Project structure

    News_Generator_RAG/
    ├── app.py
    ├── .env.example
    ├── .gitignore
    ├── pyproject.toml
    ├── requirements.txt
    ├── README.md
    ├── .streamlit/
    │   └── config.toml
    ├── src/
    │   └── gta_researcher/
    │       ├── __init__.py
    │       ├── config.py
    │       ├── collectors.py
    │       ├── groq_service.py
    │       ├── models.py
    │       ├── pipeline.py
    │       ├── scoring.py
    │       └── storage.py
    └── tests/
        ├── __init__.py
        ├── test_collectors.py
        ├── test_scoring.py
        └── test_storage.py

## Requirements

- Python 3.10 or later.
- A Groq API key from https://console.groq.com/keys.
- Internet connection for source collection and Groq requests.

No NVIDIA GPU or local model is required.

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

## How to use it

1. Enter your Groq API key in the sidebar or configure it in .env.
2. Test the Groq connection.
3. Open Sources and enable the sources you want to scan.
4. Add other RSS feeds or webpages when needed.
5. Open Research dashboard and run a scan.
6. Groq analyses collected article content and creates discoveries.
7. Open Discoveries to read ideas, edit hooks/scripts, regenerate scripts and approve useful ideas.
8. Open Production queue to download approved voiceover scripts and mark completed ideas as used.

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

The app uses a local SQLite database by default. Some cloud environments have ephemeral local storage, so use a persistent database service before relying on cloud deployment for long-term storage.

## Tests

Run:

    python -m unittest discover -s tests -v

The tests do not call Groq or make external network requests.
