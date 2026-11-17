"""Streamlit dashboard for GTA VI source research and short-form scripts."""

from __future__ import annotations

import os
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

import streamlit as st

from gta_researcher.clip_dashboard import (
    list_clip_candidates,
    number_value,
    transcript_text,
    update_clip_review_status,
)
from gta_researcher.config import DEFAULT_MODEL, get_settings
from gta_researcher.groq_service import GroqResearcher
from gta_researcher.pipeline import analyze_pending_articles, run_research_cycle
from gta_researcher.storage import ResearchStore
from gta_researcher.video_editor import (
    PLATFORMS,
    TONES,
    VIDEO_TYPES,
    editing_pack_markdown,
    generate_editing_pack,
    load_editing_pack,
    save_editing_pack,
)

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

tabs = st.tabs(["Research dashboard", "Sources", "Discoveries", "Production queue", "Live Clips"])

with tabs[0]:
    st.subheader("Research dashboard")
    st.write(
        "Scan configured websites and RSS feeds. Groq extracts ideas, explains them in simple "
        "language, scores their content potential and drafts short-form scripts."
    )
    article_counts = store.article_status_counts()
    pending_count = article_counts["pending"]
    failed_count = article_counts["failed"]
    retryable_count = pending_count + failed_count

    status_cols = st.columns(2)
    status_cols[0].metric("Articles waiting for AI analysis", pending_count)
    status_cols[1].metric("Failed analyses", failed_count)

    if st.button(
        "🔎 Scan sources and research new articles",
        type="primary",
        use_container_width=True,
        disabled=not api_key.strip(),
        help="Collect configured sources, save new articles and analyse pending or previously failed articles with Groq.",
    ):
        st.session_state["last_research_run"] = {
            "status": "running",
            "kind": "full",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "model": model.strip(),
        }
        try:
            researcher = get_researcher(api_key, model)
            with st.spinner("Collecting articles and generating video ideas with Groq..."):
                result = run_research_cycle(store, settings, researcher)
            st.session_state["last_research_run"] = {
                "status": "completed",
                "kind": "full",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "model": model.strip(),
                "summary": asdict(result),
            }
        except Exception as exc:
            st.session_state["last_research_run"] = {
                "status": "failed",
                "kind": "full",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "model": model.strip(),
                "error": f"{type(exc).__name__}: {exc}",
            }

    if st.button(
        "Analyse pending articles / retry failed analyses",
        use_container_width=True,
        disabled=not api_key.strip() or retryable_count == 0,
        help="Analyse new articles and retry articles whose previous Groq analysis failed.",
    ):
        st.session_state["last_research_run"] = {
            "status": "running",
            "kind": "analysis",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "model": model.strip(),
        }
        try:
            with st.spinner("Generating discoveries with Groq..."):
                result = analyze_pending_articles(
                    store, get_researcher(api_key, model), limit=30
                )
            st.session_state["last_research_run"] = {
                "status": "completed",
                "kind": "analysis",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "model": model.strip(),
                "summary": asdict(result),
            }
        except Exception as exc:
            st.session_state["last_research_run"] = {
                "status": "failed",
                "kind": "analysis",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "model": model.strip(),
                "error": f"{type(exc).__name__}: {exc}",
            }

    last_run = st.session_state.get("last_research_run")
    if last_run:
        with st.container(border=True):
            run_title = (
                "Last source scan" if last_run.get("kind") == "full"
                else "Last article analysis"
            )
            st.markdown(f"**{run_title}**")
            completed_at = last_run.get("completed_at") or last_run.get("started_at")
            if completed_at:
                try:
                    display_time = datetime.fromisoformat(
                        completed_at.replace("Z", "+00:00")
                    ).astimezone().strftime("%d %b %Y, %I:%M:%S %p %Z")
                except (TypeError, ValueError):
                    display_time = completed_at
                st.caption(f"Updated {display_time} · Model: {last_run.get('model') or 'Unknown'}")

            if last_run.get("status") == "running":
                st.info("Research is running. Its result will appear here when the operation finishes.")
            elif last_run.get("status") == "failed":
                st.error(f"Research operation failed: {last_run.get('error', 'Unknown error')}")
            elif last_run.get("status") == "completed":
                summary = last_run.get("summary", {})
                if last_run.get("kind") == "full":
                    st.success(
                        f"Checked {summary.get('sources_checked', 0)} sources, found "
                        f"{summary.get('articles_found', 0)} article entries "
                        f"({summary.get('articles_new', 0)} new), analysed "
                        f"{summary.get('articles_analyzed', 0)} articles and saved "
                        f"{summary.get('discoveries_saved', 0)} ideas."
                    )
                else:
                    st.success(
                        f"Analysed {summary.get('articles_analyzed', 0)} articles and saved "
                        f"{summary.get('discoveries_saved', 0)} ideas."
                    )
                errors = summary.get("errors") or []
                if errors:
                    st.warning(
                        f"{len(errors)} source or article operation(s) reported an error. "
                        "The details are available below."
                    )
                    with st.expander("View scan and analysis errors", expanded=True):
                        for error in errors:
                            st.error(error)
                elif (
                    summary.get("articles_analyzed", 0) == 0
                    and summary.get("discoveries_saved", 0) == 0
                ):
                    st.info(
                        "The run completed without saved ideas. Check that sources are active, "
                        "that they contain GTA VI-related content and that articles have readable text."
                    )

    failed_articles = store.list_failed_articles(limit=30)
    if failed_count:
        with st.expander(f"Failed article analyses ({failed_count})", expanded=False):
            if not failed_articles:
                st.info("No failed article records were returned.")
            for failed_article in failed_articles:
                st.markdown(f"**{failed_article.get('title') or 'Untitled article'}**")
                st.caption(
                    f"{failed_article.get('source_name', 'Unknown source')} · "
                    f"{failed_article.get('url', '')}"
                )
                st.error(failed_article.get("ai_error") or "No error details were recorded.")
                st.divider()

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

with tabs[4]:
    st.subheader("Live clip review")
    st.write(
        "Review candidate clips created by the local FFmpeg worker. Select a clip to preview "
        "the footage, inspect chat activity and transcripts, then approve or reject it."
    )

    clips_value = os.getenv("LIVE_CLIPS_DIR", "data/live_clips").strip() or "data/live_clips"
    clips_dir = Path(clips_value).expanduser()
    if not clips_dir.is_absolute():
        clips_dir = PROJECT_ROOT / clips_dir
    st.caption(f"Clip folder: {clips_dir}")

    toolbar_left, toolbar_right = st.columns([4, 1])
    with toolbar_left:
        review_filter = st.selectbox(
            "Review status",
            ["all", "pending", "approved", "rejected"],
            key="live_clip_review_filter",
        )
    with toolbar_right:
        st.write("")
        if st.button("Refresh clips", use_container_width=True, key="refresh_live_clips"):
            st.rerun()

    candidates = list_clip_candidates(clips_dir)
    pending_clips = sum(item.review_status == "pending" for item in candidates)
    approved_clips = sum(item.review_status == "approved" for item in candidates)
    rejected_clips = sum(item.review_status == "rejected" for item in candidates)

    clip_metrics = st.columns(4)
    clip_metrics[0].metric("Total clips", len(candidates))
    clip_metrics[1].metric("Pending review", pending_clips)
    clip_metrics[2].metric("Approved", approved_clips)
    clip_metrics[3].metric("Rejected", rejected_clips)

    visible_candidates = [
        item for item in candidates
        if review_filter == "all" or item.review_status == review_filter
    ]
    if not visible_candidates:
        st.info(
            "No clips match this filter yet. Start the local live clipper to generate candidates."
        )
        st.code(
            "python scripts/run_live_clipper.py --channel YOUR_CHANNEL --confirm-rights",
            language="powershell",
        )
    else:
        clip_labels = [item.clip_path.name for item in visible_candidates]
        selected_label = st.selectbox(
            "Choose a candidate clip",
            clip_labels,
            key="selected_live_clip",
        )
        selected_clip = next(
            item for item in visible_candidates if item.clip_path.name == selected_label
        )
        metadata = selected_clip.metadata

        timestamp_value = metadata.get("timestamp_utc", "")
        try:
            timestamp_display = datetime.fromisoformat(
                str(timestamp_value).replace("Z", "+00:00")
            ).astimezone().strftime("%d %b %Y, %I:%M:%S %p %Z")
        except (TypeError, ValueError):
            timestamp_display = datetime.fromtimestamp(
                number_value(metadata.get("timestamp", 0)), timezone.utc
            ).astimezone().strftime("%d %b %Y, %I:%M:%S %p %Z")

        st.markdown(f"### {selected_clip.clip_path.stem}")
        st.caption(
            f"Detected: {timestamp_display} · Review status: {selected_clip.review_status.title()}"
        )

        preview_col, details_col = st.columns([1.35, 1])
        with preview_col:
            try:
                st.video(str(selected_clip.clip_path))
                st.download_button(
                    "Download selected MP4",
                    data=selected_clip.clip_path.read_bytes(),
                    file_name=selected_clip.clip_path.name,
                    mime="video/mp4",
                    key=f"download_clip_{selected_clip.clip_path.stem}",
                    use_container_width=True,
                )
            except OSError as exc:
                st.warning(f"Could not load this clip: {exc}")

        with details_col:
            detail_metrics = st.columns(2)
            detail_metrics[0].metric(
                "Chat messages",
                int(number_value(metadata.get("messages_in_bucket", 0))),
            )
            detail_metrics[1].metric(
                "Activity ratio",
                f"{number_value(metadata.get('activity_ratio', 0)):.1f}x",
            )
            st.caption(
                f"Baseline median: {number_value(metadata.get('baseline_median', 0)):.1f} "
                "messages / bucket"
            )
            st.caption(
                f"Baseline MAD: {number_value(metadata.get('baseline_mad', 0)):.1f} · "
                f"Detection threshold: {number_value(metadata.get('threshold', 0)):.1f}"
            )
            st.caption(
                f"Event bucket starts at: {number_value(metadata.get('bucket_start', 0)):.1f}s "
                "on the recorder timeline"
            )
            st.caption(f"File size: {selected_clip.clip_path.stat().st_size / (1024 * 1024):.1f} MB")

        if selected_clip.transcript:
            with st.expander("Transcript", expanded=True):
                text_value = transcript_text(selected_clip.transcript)
                language = selected_clip.transcript.get("language", "unknown")
                st.caption(f"Detected language: {language}")
                if text_value:
                    st.write(text_value)
                    st.download_button(
                        "Download transcript",
                        data=text_value,
                        file_name=f"{selected_clip.clip_path.stem}_transcript.txt",
                        mime="text/plain",
                        key=f"download_transcript_{selected_clip.clip_path.stem}",
                    )
                else:
                    st.info("The transcript file exists but contains no readable text.")
                segments = selected_clip.transcript.get("segments", [])
                if isinstance(segments, list) and segments:
                    with st.expander("Transcript timestamps"):
                        for segment in segments:
                            if not isinstance(segment, dict):
                                continue
                            start_seconds = number_value(segment.get("start", 0))
                            end_seconds = number_value(segment.get("end", 0))
                            segment_text = str(segment.get("text", "")).strip()
                            if segment_text:
                                st.caption(f"{start_seconds:05.1f}s – {end_seconds:05.1f}s")
                                st.write(segment_text)
        else:
            st.info(
                "No transcript found for this clip. Install the transcription extra and run "
                "scripts/transcribe_clips.py against the clip folder."
            )

        st.divider()
        st.subheader("🎬 Video editing assistant")
        st.write(
            "Choose the kind of edit you are making. The assistant uses this clip's transcript "
            "and chat metadata to prepare hooks, timed overlays, captions, hashtags, mentions, "
            "thumbnail direction and a practical editing plan."
        )

        editor_col1, editor_col2, editor_col3 = st.columns(3)
        with editor_col1:
            video_type = st.selectbox(
                "What kind of video is this?",
                list(VIDEO_TYPES),
                key=f"editor_type_{selected_clip.clip_path.stem}",
            )
        with editor_col2:
            target_platform = st.selectbox(
                "Where will you post it?",
                PLATFORMS,
                index=3,
                key=f"editor_platform_{selected_clip.clip_path.stem}",
            )
        with editor_col3:
            editing_tone = st.selectbox(
                "Editing style",
                TONES,
                index=0,
                key=f"editor_tone_{selected_clip.clip_path.stem}",
            )

        st.caption(
            "Groq AI is used when a key is configured. Without it, the app generates a useful "
            "local starter pack. Suggestions are editable and should be checked against the actual footage."
        )
        if st.button(
            "✨ Generate editing suggestions",
            type="primary",
            key=f"generate_editor_pack_{selected_clip.clip_path.stem}",
            use_container_width=True,
        ):
            transcript_for_editor = transcript_text(selected_clip.transcript)
            try:
                with st.spinner("Building your video editing package..."):
                    editing_pack = generate_editing_pack(
                        api_key=api_key,
                        model=model,
                        video_type=video_type,
                        platform=target_platform,
                        tone=editing_tone,
                        clip_name=selected_clip.clip_path.name,
                        transcript=transcript_for_editor,
                        metadata=metadata,
                    )
                save_editing_pack(selected_clip.clip_path, editing_pack)
                st.session_state[f"editor_pack_notice_{selected_clip.clip_path.stem}"] = (
                    editing_pack.get("generation_mode", "Generated")
                )
                st.rerun()
            except Exception as exc:
                st.warning(
                    f"Groq generation failed ({type(exc).__name__}). A local starter package "
                    "has been created instead, so you can still work on the edit."
                )
                try:
                    fallback_pack = generate_editing_pack(
                        api_key="",
                        model=model,
                        video_type=video_type,
                        platform=target_platform,
                        tone=editing_tone,
                        clip_name=selected_clip.clip_path.name,
                        transcript=transcript_text(selected_clip.transcript),
                        metadata=metadata,
                    )
                    fallback_pack["generation_mode"] = "local fallback (Groq unavailable)"
                    save_editing_pack(selected_clip.clip_path, fallback_pack)
                    st.rerun()
                except Exception as fallback_exc:
                    st.error(
                        f"Could not create local suggestions: "
                        f"{type(fallback_exc).__name__}: {fallback_exc}"
                    )

        saved_pack = load_editing_pack(selected_clip.clip_path)
        if saved_pack:
            notice_key = f"editor_pack_notice_{selected_clip.clip_path.stem}"
            generation_notice = st.session_state.pop(notice_key, saved_pack.get("generation_mode", "Saved"))
            st.caption(
                f"Loaded editing package · {generation_notice} · "
                f"{saved_pack.get('video_type', 'Video type not recorded')} · "
                f"{saved_pack.get('platform', 'Platform not recorded')}"
            )
            st.markdown(f"**Working title:** {saved_pack.get('video_title', selected_clip.clip_path.stem)}")
            st.markdown("**Opening hook**")
            hook_key = f"editor_hook_{selected_clip.clip_path.stem}"
            if hook_key not in st.session_state:
                st.session_state[hook_key] = str(saved_pack.get("hook", ""))
            st.text_input("Hook text", key=hook_key)

            with st.expander("On-screen text and timing", expanded=True):
                overlay_items = saved_pack.get("on_screen_text", [])
                if overlay_items:
                    for index, overlay in enumerate(overlay_items):
                        if isinstance(overlay, dict):
                            st.markdown(
                                f"**{overlay.get('time', 'Timing to confirm')}**  "
                                f"{overlay.get('text', '')}"
                            )
                else:
                    st.info("No overlay text was returned. Add captions that match the footage.")

            with st.expander("Post caption, hashtags and mentions", expanded=True):
                caption_key = f"editor_caption_{selected_clip.clip_path.stem}"
                if caption_key not in st.session_state:
                    st.session_state[caption_key] = str(saved_pack.get("caption", ""))
                st.text_area("Post caption (editable)", key=caption_key, height=130)
                hashtags = saved_pack.get("hashtags", [])
                hashtag_text = " ".join(str(tag) for tag in hashtags)
                st.text_input(
                    "Hashtags (copy and edit)",
                    value=hashtag_text,
                    key=f"editor_hashtags_{selected_clip.clip_path.stem}",
                )
                mentions = saved_pack.get("mentions", [])
                st.markdown("**Mention / credit suggestions**")
                for mention in mentions:
                    st.markdown(f"- {mention}")

            with st.expander("Thumbnail concept", expanded=True):
                thumbnail = saved_pack.get("thumbnail", {})
                if isinstance(thumbnail, dict):
                    st.markdown(f"**Thumbnail text:** {thumbnail.get('title', '')}")
                    st.write(thumbnail.get("composition", ""))
                    st.caption(f"Text placement: {thumbnail.get('text_placement', '')}")
                    st.caption(f"Style: {thumbnail.get('style', '')}")

            with st.expander("Editing timeline and audio", expanded=True):
                for beat in saved_pack.get("editing_timeline", []):
                    if isinstance(beat, dict):
                        st.markdown(f"**{beat.get('time', '')}**")
                        st.write(beat.get("instruction", ""))
                st.markdown("**Audio mix**")
                st.write(saved_pack.get("audio", ""))

            st.markdown("**Suggested ending / CTA**")
            st.write(saved_pack.get("call_to_action", ""))
            st.markdown("**Final editing checklist**")
            for check in saved_pack.get("editing_checklist", []):
                st.markdown(f"- {check}")

            if st.button(
                "Save my caption and hook edits",
                key=f"save_editor_edits_{selected_clip.clip_path.stem}",
            ):
                updated_pack = dict(saved_pack)
                updated_pack["hook"] = st.session_state[hook_key]
                updated_pack["caption"] = st.session_state[caption_key]
                updated_pack["hashtags"] = [
                    tag for tag in st.session_state[
                        f"editor_hashtags_{selected_clip.clip_path.stem}"
                    ].split() if tag
                ]
                save_editing_pack(selected_clip.clip_path, updated_pack)
                st.success("Your edits have been saved with this clip.")
                st.rerun()

            st.download_button(
                "Download complete editing brief (.md)",
                data=editing_pack_markdown(saved_pack),
                file_name=f"{selected_clip.clip_path.stem}_editing_brief.md",
                mime="text/markdown",
                key=f"download_editing_brief_{selected_clip.clip_path.stem}",
                use_container_width=True,
            )
        else:
            st.info("Generate a package to see tailored hooks, overlays, social copy, thumbnail direction and editing instructions here.")

        action_left, action_right, action_note = st.columns([1, 1, 3])
        with action_left:
            if st.button(
                "Approve clip",
                key=f"approve_clip_{selected_clip.clip_path.stem}",
                disabled=selected_clip.review_status == "approved",
                use_container_width=True,
            ):
                try:
                    update_clip_review_status(selected_clip, "approved")
                    st.success("Clip approved.")
                    st.rerun()
                except (OSError, ValueError) as exc:
                    st.error(f"Could not save review status: {exc}")
        with action_right:
            if st.button(
                "Reject clip",
                key=f"reject_clip_{selected_clip.clip_path.stem}",
                disabled=selected_clip.review_status == "rejected",
                use_container_width=True,
            ):
                try:
                    update_clip_review_status(selected_clip, "rejected")
                    st.success("Clip rejected.")
                    st.rerun()
                except (OSError, ValueError) as exc:
                    st.error(f"Could not save review status: {exc}")
        with action_note:
            st.caption(
                "Review decisions are saved in the clip's JSON sidecar and remain available "
                "after the dashboard is restarted."
            )


st.divider()
st.caption(
    "Research suggestions are AI-generated and not independently verified. Review the source, "
    "check factual claims and clear content rights before publishing."
)
