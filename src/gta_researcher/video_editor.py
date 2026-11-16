"""Generate and persist practical short-form video editing suggestions."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from groq import Groq

from gta_researcher.groq_service import _parse_json_object


VIDEO_TYPES = {
    "Emotional / nostalgia": "A cinematic, reflective moment designed to create nostalgia and emotional connection.",
    "Funny moment / fail": "A fast-paced funny moment with a clear setup, payoff and replay value.",
    "Gameplay highlight": "A high-energy gameplay moment that makes the action immediately understandable.",
    "Streamer reaction": "A creator reaction clip where the reaction and context are the main story.",
    "Cinematic drive / atmosphere": "A visually led cinematic edit focused on mood, scenery and immersion.",
    "NPC behaviour / hidden detail": "A curiosity-led discovery that explains an observable in-game detail.",
    "Myth / challenge": "A test or challenge with a clear question, evidence and result.",
    "News / update / explainer": "A concise factual explainer that distinguishes confirmed information from speculation.",
    "Story / mission moment": "A short narrative beat with enough context to make the moment understandable.",
}

PLATFORMS = ["Instagram Reels", "YouTube Shorts", "TikTok", "All vertical platforms"]
TONES = ["Cinematic", "Funny", "High energy", "Mysterious", "Informative", "Emotional"]


def _fallback_pack(
    video_type: str, platform: str, transcript: str, clip_name: str
) -> dict[str, Any]:
    """Useful local suggestions when Groq is not configured or is unavailable."""
    transcript_hint = transcript.strip().replace("\n", " ")
    transcript_hint = transcript_hint[:180]
    hooks = {
        "Emotional / nostalgia": "Some places in games just stay with you.",
        "Funny moment / fail": "Wait for what happens next…",
        "Gameplay highlight": "That escalated quickly.",
        "Streamer reaction": "The reaction says it all.",
        "Cinematic drive / atmosphere": "Take a moment and enjoy the view.",
        "NPC behaviour / hidden detail": "Have you ever noticed this in Los Santos?",
        "Myth / challenge": "Let's see if this actually works.",
        "News / update / explainer": "Here's what you need to know.",
        "Story / mission moment": "This moment hits differently when you know the story.",
    }
    hook = hooks.get(video_type, "Watch this moment.")
    if transcript_hint:
        hook = f"{hook} Listen closely."
    return {
        "video_title": clip_name.rsplit(".", 1)[0].replace("_", " "),
        "hook": hook,
        "on_screen_text": [
            {"time": "0:00–0:02", "text": hook},
            {"time": "0:03–0:08", "text": "Stay for the moment"},
            {"time": "Final 2 seconds", "text": "What would you do?"},
        ],
        "caption": (
            f"{hook}\n\nWhat was your favourite moment in GTA?\n\n"
            "#GTA #GTAV #Gaming"
        ),
        "hashtags": ["#GTA", "#GTAV", "#GTAOnline", "#Gaming", "#GamingClips", "#RockstarGames"],
        "mentions": [
            "Mention the creator only if this is their clip and you have permission.",
            "You can reference Rockstar Games as the game publisher; verify the current official account before tagging.",
        ],
        "thumbnail": {
            "title": hook[:48],
            "composition": "Use the clearest frame showing the main subject or action. Keep the subject away from the lower-right UI area.",
            "text_placement": "Large 3–5 word title in the upper third with a dark outline for contrast.",
            "style": "High contrast, one focal point, minimal text; avoid clutter.",
        },
        "editing_timeline": [
            {"time": "0:00–0:02", "instruction": "Open on the strongest frame. Add the hook as large text; avoid a logo intro."},
            {"time": "0:02–0:08", "instruction": "Keep the context concise. Use clean cuts and readable subtitles if dialogue is present."},
            {"time": "0:08–0:20", "instruction": "Let the main moment play. Add a subtle punch-in only when it improves focus."},
            {"time": "Final 2 seconds", "instruction": "End on the payoff and add one short question or CTA."},
        ],
        "audio": "Keep important game audio or dialogue audible. Lower background music beneath speech; use only music and effects you have rights to use.",
        "call_to_action": "What would you have done in this situation?",
        "editing_checklist": [
            "Use a 9:16 canvas and keep important action inside the safe area.",
            "Add accurate subtitles and correct any automatic transcription errors.",
            "Remove dead air and avoid excessive transitions.",
            "Check that the first frame communicates the subject immediately.",
            "Review the final export with sound on and off.",
        ],
        "platform": platform,
        "video_type": video_type,
        "generation_mode": "local fallback",
    }


def generate_editing_pack(
    *,
    api_key: str,
    model: str,
    video_type: str,
    platform: str,
    tone: str,
    clip_name: str,
    transcript: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate a structured edit plan grounded in the selected clip's context."""
    if video_type not in VIDEO_TYPES:
        raise ValueError("Choose a supported video type.")
    if platform not in PLATFORMS:
        raise ValueError("Choose a supported publishing platform.")
    if tone not in TONES:
        raise ValueError("Choose a supported editing tone.")

    context = {
        "clip_filename": clip_name,
        "video_type": video_type,
        "video_type_guidance": VIDEO_TYPES[video_type],
        "platform": platform,
        "tone": tone,
        "transcript": transcript[:5000],
        "clip_metadata": {
            key: (metadata or {}).get(key)
            for key in (
                "channel", "creator", "timestamp_utc", "messages_in_bucket",
                "activity_ratio", "bucket_start"
            )
            if (metadata or {}).get(key) is not None
        },
    }
    fallback = _fallback_pack(video_type, platform, transcript, clip_name)
    if not api_key.strip():
        return fallback

    prompt = f"""
Create a practical editing package for a short gaming video. Use the clip context below.
Do not claim to have visually inspected the video. You only have its filename, optional
transcript and metadata. Do not invent events, dialogue, creator identities, account handles,
game facts or endorsements. If the transcript is empty, make text suggestions generic and
tell the editor to align them to what is actually visible. Hashtags should be relevant, not spam.
Mentions must be names to consider, not fabricated @handles; include a creator mention only
when the creator is explicitly identified in the metadata and advise permission/credit.

Return one valid JSON object with exactly these fields:
{{
 "video_title": "working title",
 "hook": "opening line for first 1-3 seconds",
 "on_screen_text": [{{"time":"0:00-0:02","text":"short overlay"}}],
 "caption": "ready-to-post caption with a natural CTA",
 "hashtags": ["#RelevantTag"],
 "mentions": ["who to consider mentioning and why; no guessed handles"],
 "thumbnail": {{"title":"short thumbnail words","composition":"specific frame/composition idea","text_placement":"where text goes","style":"visual treatment"}},
 "editing_timeline": [{{"time":"0:00-0:02","instruction":"specific editing action"}}],
 "audio": "music, game audio, voice and sound effect mix guidance",
 "call_to_action": "one natural comment/follow prompt",
 "editing_checklist": ["specific quality check"]
}}
Aim for 6-10 hashtags, 2-4 thumbnail text words, 3-6 on-screen text beats and 4-6 timeline beats.
Keep overlay text short enough to read on a phone. Make the package specific to the chosen video type.
Context:
{json.dumps(context, ensure_ascii=False)}
""".strip()

    client = Groq(api_key=api_key.strip(), timeout=45.0, max_retries=2)
    completion = client.chat.completions.create(
        model=model.strip(),
        messages=[
            {
                "role": "system",
                "content": "You are an experienced short-form gaming video editor and social strategist. Return only valid JSON.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.55,
        max_completion_tokens=1600,
        response_format={"type": "json_object"},
    )
    payload = _parse_json_object(completion.choices[0].message.content or "{}")
    # Keep the UI predictable if the model omits or mis-types a field.
    for key, default in fallback.items():
        payload.setdefault(key, default)
    for key in ("video_title", "hook", "caption", "audio", "call_to_action"):
        if not isinstance(payload.get(key), str):
            payload[key] = str(fallback[key])
    for key in ("on_screen_text", "hashtags", "mentions", "editing_timeline", "editing_checklist"):
        if not isinstance(payload.get(key), list):
            payload[key] = fallback[key]
    payload["on_screen_text"] = [
        item for item in payload["on_screen_text"] if isinstance(item, dict)
    ]
    payload["editing_timeline"] = [
        item for item in payload["editing_timeline"] if isinstance(item, dict)
    ]
    payload["hashtags"] = [str(item) for item in payload["hashtags"] if str(item).strip()]
    payload["mentions"] = [str(item) for item in payload["mentions"] if str(item).strip()]
    payload["editing_checklist"] = [
        str(item) for item in payload["editing_checklist"] if str(item).strip()
    ]
    if not isinstance(payload.get("thumbnail"), dict):
        payload["thumbnail"] = fallback["thumbnail"]
    else:
        for key, default in fallback["thumbnail"].items():
            payload["thumbnail"].setdefault(key, default)
    payload["video_type"] = video_type
    payload["platform"] = platform
    payload["generation_mode"] = "Groq AI"
    return payload


def save_editing_pack(clip_path: str | Path, payload: dict[str, Any]) -> Path:
    """Persist suggestions beside the clip without modifying its review metadata."""
    clip = Path(clip_path).expanduser().resolve()
    destination = clip.with_suffix(".editor.json")
    temporary = destination.with_suffix(".editor.json.tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(destination)
    return destination


def load_editing_pack(clip_path: str | Path) -> dict[str, Any] | None:
    """Load a previously generated editing package, ignoring malformed sidecars."""
    clip = Path(clip_path).expanduser().resolve()
    sidecar = clip.with_suffix(".editor.json")
    try:
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def editing_pack_markdown(payload: dict[str, Any]) -> str:
    """Render an editing package as a portable Markdown production brief."""
    lines = [
        f"# {payload.get('video_title', 'Video editing package')}",
        "",
        f"**Video type:** {payload.get('video_type', '')}",
        f"**Platform:** {payload.get('platform', '')}",
        f"**Hook:** {payload.get('hook', '')}",
        "",
        "## On-screen text",
    ]
    for item in payload.get("on_screen_text", []):
        if isinstance(item, dict):
            lines.append(f"- **{item.get('time', '')}** {item.get('text', '')}")
    lines.extend(["", "## Caption", str(payload.get("caption", "")), "", "## Hashtags"])
    lines.append(" ".join(payload.get("hashtags", [])))
    lines.extend(["", "## Mentions"])
    lines.extend(f"- {item}" for item in payload.get("mentions", []))
    lines.extend(["", "## Thumbnail"])
    thumbnail = payload.get("thumbnail", {})
    if isinstance(thumbnail, dict):
        for key in ("title", "composition", "text_placement", "style"):
            lines.append(f"- **{key.replace('_', ' ').title()}:** {thumbnail.get(key, '')}")
    lines.extend(["", "## Editing timeline"])
    for item in payload.get("editing_timeline", []):
        if isinstance(item, dict):
            lines.append(f"- **{item.get('time', '')}** {item.get('instruction', '')}")
    lines.extend(["", "## Audio", str(payload.get("audio", "")), "", "## Call to action", str(payload.get("call_to_action", "")), "", "## Final checklist"])
    lines.extend(f"- [ ] {item}" for item in payload.get("editing_checklist", []))
    return "\n".join(lines).strip() + "\n"
