"""Streamlit dashboard for GTA VI source research and short-form scripts."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

import streamlit as st

from gta_researcher.config import DEFAULT_MODEL, get_settings
from gta_researcher.groq_service import GroqResearcher
from gta_researcher.pipeline import analyze_pending_articles, run_research_cycle
from gta_researcher.storage import ResearchStore

st.set_page_config(page_title="GTA VI News Researcher", page_icon="🎮", layout="wide")
settings = get_settings()


@st.cache_resource
def get_store(database_path: str) -> ResearchStore:
    return ResearchStore(database_path)


store = get_store(str(settings.database_path))


def read_secret_api_key() -> str:
    if settings.groq_api_key:
        return settings.groq_api_key
    try:
        return str(st.secrets.get("GROQ_API_KEY", "")).strip()
    except Exception:
        return ""


def get_researcher(api_key: str, model: str) -> GroqResearcher:
    return GroqResearcher(api_key=api_key, model=model)


def render_discovery(item: dict, api_key: str, model: str) -> None:
    score = float(item.get("overall_score") or 0)
    with st.expander(f"{item['title']}  ·  {score:.1f}/10"):
        st.caption(
            f"{item.get('series', 'GTA VI')}  •  {item.get('category', 'Discovery')}  •  "
            f"Status: {item.get('status', 'new')}"
        )
        st.write(item.get("claim", ""))
        if item.get("explanation"):
            st.write(item["explanation"])
        st.markdown(f"**Why it is interesting:** {item.get('why_interesting') or 'Not specified'}")
        st.markdown(f"**Video angle:** {item.get('clip_angle') or 'Not specified'}")
        st.markdown(f"**Suggested hook:** {item.get('hook') or 'Not generated'}")
        source_url = item.get("source_url", "")
        source_name = item.get("source_name", "Open source")
        if source_url:
            st.markdown(f"**Source:** [{source_name}]({source_url})")
        st.caption(
            f"Novelty {item.get('novelty_score', 5)}/10 · "
            f"Shareability {item.get('shareability_score', 5)}/10 · "
            f"Visual potential {item.get('visual_potential_score', 5)}/10 · "
            f"AI-estimated confidence {item.get('confidence', 50)}%"
        )
        if item.get("evidence_type"):
            st.caption(f"Source classification: {item['evidence_type']}")
        if item.get("visual_notes"):
            st.markdown(f"**Visual notes:** {item['visual_notes']}")
        if item.get("hashtags"):
            st.caption(" ".join(item["hashtags"]))

        discovery_id = item["id"]
        hook_key = f"hook_{discovery_id}"
        script_key = f"script_{discovery_id}"
        visual_key = f"visual_{discovery_id}"
        pending_key = f"pending_generated_{discovery_id}"
        pending_generated = st.session_state.pop(pending_key, None)
        if pending_generated:
            st.session_state[hook_key] = pending_generated["hook"]
            st.session_state[script_key] = pending_generated["script"]
            st.session_state[visual_key] = pending_generated["visual_notes"]
        st.text_input("Video hook", value=item.get("hook", ""), key=hook_key)
        st.text_area(
            "Voiceover script",
            value=item.get("script", ""),
            height=180,
            key=script_key,
        )
        st.text_area(
            "Editing / visual notes",
            value=item.get("visual_notes", ""),
            height=100,
            key=visual_key,
        )

        left, middle, right = st.columns(3)
        with left:
            if st.button("Approve idea", key=f"approve_{discovery_id}", use_container_width=True):
                store.update_discovery_status(discovery_id, "approved")
                st.rerun()
        with middle:
            if st.button("Reject", key=f"reject_{discovery_id}", use_container_width=True):
                store.update_discovery_status(discovery_id, "rejected")
                st.rerun()
        with right:
            if st.button("Save edits", key=f"save_{discovery_id}", use_container_width=True):
                store.update_discovery_script(
                    discovery_id,
                    st.session_state[hook_key],
                    st.session_state[script_key],
                    st.session_state[visual_key],
                )
                st.success("Changes saved.")

        if api_key.strip() and st.button(
            "Regenerate script with Groq", key=f"regen_{discovery_id}"
        ):
            try:
                with st.spinner("Generating a fresh script..."):
                    generated = get_researcher(api_key, model).generate_short_script(
                        item, target_seconds=30
                    )
                store.update_discovery_script(
                    discovery_id,
                    generated["hook"],
                    generated["script"],
                    generated["visual_notes"],
                )
                st.session_state[pending_key] = generated
                st.success("New script generated.")
                st.rerun()
            except Exception as exc:
                st.error(f"Script generation failed: {type(exc).__name__}: {exc}")

        st.download_button(
            "Download script as TXT",
            data=(
                f"{item.get('hook', '')}\n\n{item.get('script', '')}\n\n"
                f"Visual notes: {item.get('visual_notes', '')}\n\n"
                f"Source: {source_url}\n"
            ),
            file_name=f"gta_vi_script_{discovery_id}.txt",
            mime="text/plain",
            key=f"download_{discovery_id}",
        )


st.title("🎮 GTA VI News Researcher")
st.write(
    "Find interesting GTA VI facts, gameplay details and discoveries, then turn them into "
    "short-form video ideas with Groq."
)

with st.sidebar:
    st.header("Groq configuration")
    api_key = st.text_input(
        "Groq API key",
        value=read_secret_api_key(),
        type="password",
        help="Use .env, Streamlit secrets or this session-only field.",
    )
    model = st.text_input(
        "Groq model ID",
        value=settings.groq_model or DEFAULT_MODEL,
        help="Choose a model enabled for your Groq account.",
    )
    if st.button("Test Groq connection", use_container_width=True):
        if not api_key.strip():
            st.error("Add your Groq API key first.")
        else:
            try:
                with st.spinner("Checking Groq access..."):
                    available = get_researcher(api_key, model).test_connection()
                st.success("Groq API key is valid.")
                st.caption("Models visible to your key:")
                st.code("\n".join(available[:30]))
            except Exception as exc:
                st.error(f"Groq connection failed: {type(exc).__name__}: {exc}")

    st.divider()
    st.caption("AI analysis runs through Groq. No local model inference is required.")
    st.caption(f"Database: {settings.database_path.name}")

counts = store.dashboard_counts()
metric_cols = st.columns(4)
metric_cols[0].metric("Active sources", counts["sources"])
metric_cols[1].metric("Collected articles", counts["articles"])
metric_cols[2].metric("New ideas", counts["new"])
metric_cols[3].metric("Approved ideas", counts["approved"])

tabs = st.tabs(["Research dashboard", "Sources", "Discoveries", "Production queue"])

with tabs[0]:
    st.subheader("Research dashboard")
    st.write(
        "Scan configured websites and RSS feeds. Groq extracts ideas, explains them in simple "
        "language, scores their content potential and drafts short-form scripts."
    )
    pending_count = len(store.list_pending_articles(limit=200))
    st.metric("Articles waiting for AI analysis", pending_count)

    if st.button(
        "🔎 Scan sources and research new articles",
        type="primary",
        use_container_width=True,
        disabled=not api_key.strip(),
    ):
        try:
            researcher = get_researcher(api_key, model)
            with st.spinner("Collecting articles and generating video ideas with Groq..."):
                result = run_research_cycle(store, settings, researcher)
            st.success(
                f"Checked {result.sources_checked} sources, found "
                f"{result.articles_found} article entries, analysed "
                f"{result.articles_analyzed} articles and saved "
                f"{result.discoveries_saved} ideas."
            )
            for error in result.errors or []:
                st.warning(error)
            st.rerun()
        except Exception as exc:
            st.error(f"Research cycle failed: {type(exc).__name__}: {exc}")

    if st.button(
        "Analyse pending articles only",
        use_container_width=True,
        disabled=not api_key.strip() or pending_count == 0,
    ):
        try:
            from gta_researcher.pipeline import analyze_pending_articles

            with st.spinner("Generating discoveries with Groq..."):
                result = analyze_pending_articles(
                    store, get_researcher(api_key, model), limit=30
                )
            st.success(
                f"Analysed {result.articles_analyzed} articles and saved "
                f"{result.discoveries_saved} ideas."
            )
            for error in result.errors or []:
                st.warning(error)
            st.rerun()
        except Exception as exc:
            st.error(f"Analysis failed: {type(exc).__name__}: {exc}")

    st.subheader("Highest-scoring new ideas")
    recent = store.list_discoveries(status="new", limit=8)
    if not recent:
        st.info("No discoveries yet. Enable sources and run your first research scan.")
    for item in recent:
        st.markdown(
            f"- **{float(item['overall_score']):.1f}/10 · {item['title']}** — "
            f"{item.get('hook', '')}"
        )

with tabs[1]:
    st.subheader("Source manager")
    st.write("Add RSS feeds or individual webpages. Only active sources are scanned.")
    with st.form("add_source_form", clear_on_submit=True):
        source_name = st.text_input("Source name", placeholder="Example: Rockstar Newswire")
        source_url = st.text_input("Feed or webpage URL", placeholder="https://...")
        source_kind = st.selectbox("Source type", ["rss", "webpage"])
        source_description = st.text_input("Description (optional)")
        submitted = st.form_submit_button("Add source")
        if submitted:
            try:
                from gta_researcher.collectors import validate_public_url

                safe_url = validate_public_url(source_url)
                store.add_source(source_name, safe_url, source_kind, source_description)
                st.success("Source added.")
                st.rerun()
            except Exception as exc:
                st.error(f"Could not add source: {type(exc).__name__}: {exc}")

    for source in store.list_sources():
        with st.container(border=True):
            cols = st.columns([3, 4, 1])
            cols[0].markdown(f"**{source['name']}**")
            cols[0].caption(f"{source['kind']} · {source['description']}")
            cols[1].markdown(f"[{source['url']}]({source['url']})")
            if source.get("last_checked"):
                cols[1].caption(f"Last checked: {source['last_checked']}")
            if source.get("last_error"):
                cols[1].error(source["last_error"])
            is_active = bool(source["active"])
            active_value = cols[2].checkbox(
                "Active", value=is_active, key=f"source_active_{source['id']}"
            )
            if active_value != is_active:
                store.set_source_active(source["id"], active_value)
                st.rerun()

with tabs[2]:
    st.subheader("Research discoveries")
    status_filter = st.selectbox(
        "Filter by status", ["all", "new", "approved", "rejected", "used"]
    )
    discoveries = store.list_discoveries(status=status_filter, limit=150)
    if not discoveries:
        st.info("No discoveries match this filter yet.")
    for discovery in discoveries:
        render_discovery(discovery, api_key, model)

with tabs[3]:
    st.subheader("Production queue")
    approved = store.list_discoveries(status="approved", limit=100)
    if not approved:
        st.info("Approve discoveries to add them to your production queue.")
    for item in approved:
        with st.container(border=True):
            st.markdown(f"**{item['title']}**")
            st.caption(f"{item['series']} · Score {float(item['overall_score']):.1f}/10")
            st.write(item.get("script", ""))
            st.caption(f"Source: {item.get('source_url', '')}")
            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    "Download voiceover script",
                    data=item.get("script", ""),
                    file_name=f"gta_vi_voiceover_{item['id']}.txt",
                    mime="text/plain",
                    key=f"queue_download_{item['id']}",
                    use_container_width=True,
                )
            with col2:
                if st.button(
                    "Mark as used", key=f"used_{item['id']}", use_container_width=True
                ):
                    store.update_discovery_status(item["id"], "used")
                    st.rerun()

st.divider()
st.caption(
    "Research suggestions are AI-generated and not independently verified. Review the source, "
    "check factual claims and clear content rights before publishing."
)
