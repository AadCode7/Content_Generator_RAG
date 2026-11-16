import json
import tempfile
import unittest
from pathlib import Path

from gta_researcher.video_editor import (
    editing_pack_markdown,
    generate_editing_pack,
    load_editing_pack,
    save_editing_pack,
)


class VideoEditorTests(unittest.TestCase):
    def test_generates_local_fallback_without_api_key(self):
        pack = generate_editing_pack(
            api_key="",
            model="unused",
            video_type="Emotional / nostalgia",
            platform="Instagram Reels",
            tone="Cinematic",
            clip_name="los_santos_drive.mp4",
            transcript="A long drive through the city.",
            metadata={"activity_ratio": 3.2},
        )
        self.assertEqual(pack["generation_mode"], "local fallback")
        self.assertIn("hook", pack)
        self.assertTrue(pack["hashtags"])
        self.assertTrue(pack["thumbnail"]["composition"])
        self.assertTrue(pack["editing_timeline"])

    def test_rejects_unknown_video_type(self):
        with self.assertRaises(ValueError):
            generate_editing_pack(
                api_key="", model="unused", video_type="Unknown",
                platform="Instagram Reels", tone="Cinematic",
                clip_name="clip.mp4",
            )

    def test_saves_and_loads_editing_package_without_touching_clip(self):
        with tempfile.TemporaryDirectory() as directory:
            clip = Path(directory) / "clip.mp4"
            clip.write_bytes(b"fake video")
            pack = generate_editing_pack(
                api_key="", model="unused",
                video_type="Funny moment / fail",
                platform="YouTube Shorts", tone="Funny",
                clip_name=clip.name,
            )
            sidecar = save_editing_pack(clip, pack)
            self.assertEqual(sidecar.name, "clip.editor.json")
            self.assertEqual(load_editing_pack(clip)["video_type"], "Funny moment / fail")
            self.assertEqual(clip.read_bytes(), b"fake video")

    def test_ignores_malformed_saved_package(self):
        with tempfile.TemporaryDirectory() as directory:
            clip = Path(directory) / "clip.mp4"
            clip.write_bytes(b"fake video")
            clip.with_suffix(".editor.json").write_text("{broken", encoding="utf-8")
            self.assertIsNone(load_editing_pack(clip))

    def test_exports_readable_markdown(self):
        pack = generate_editing_pack(
            api_key="", model="unused",
            video_type="Gameplay highlight",
            platform="All vertical platforms", tone="High energy",
            clip_name="highlight.mp4",
        )
        markdown = editing_pack_markdown(pack)
        self.assertIn("# ", markdown)
        self.assertIn("## Thumbnail", markdown)
        self.assertIn("## Editing timeline", markdown)


if __name__ == "__main__":
    unittest.main()
