import json
import tempfile
import unittest
from pathlib import Path

from gta_researcher.clip_dashboard import (
    list_clip_candidates,
    number_value,
    transcript_text,
    update_clip_review_status,
)


class ClipDashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.clip = self.root / "creator_20261116T110000.mp4"
        self.clip.write_bytes(b"fake mp4 bytes")
        self.metadata_path = self.clip.with_suffix(".json")
        self.metadata = {
            "timestamp": 1794805200.0,
            "timestamp_utc": "2026-11-16T05:00:00+00:00",
            "messages_in_bucket": 25,
            "baseline_median": 3.0,
            "baseline_mad": 1.0,
            "activity_ratio": 8.33,
            "threshold": 8.0,
            "clip_path": str(self.clip),
        }
        self.metadata_path.write_text(json.dumps(self.metadata), encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_loads_clip_metadata_and_transcript(self):
        transcript_path = self.clip.with_suffix(".transcript.json")
        transcript_path.write_text(
            json.dumps({"language": "en", "segments": [{"text": "Amazing moment!"}]}),
            encoding="utf-8",
        )
        items = list_clip_candidates(self.root)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].metadata["messages_in_bucket"], 25)
        self.assertEqual(items[0].transcript["language"], "en")
        self.assertEqual(transcript_text(items[0].transcript), "Amazing moment!")

    def test_review_status_round_trip(self):
        item = list_clip_candidates(self.root)[0]
        self.assertEqual(item.review_status, "pending")
        update_clip_review_status(item, "approved")
        refreshed = list_clip_candidates(self.root)[0]
        self.assertEqual(refreshed.review_status, "approved")

    def test_ignores_malformed_metadata_and_transcript_sidecars(self):
        (self.root / "broken.json").write_text("{not json", encoding="utf-8")
        (self.root / "orphan.transcript.json").write_text("{}", encoding="utf-8")
        self.assertEqual(len(list_clip_candidates(self.root)), 1)

    def test_rejects_paths_outside_clip_directory(self):
        outside = self.root.parent / "outside.mp4"
        outside.write_bytes(b"not in folder")
        try:
            payload = dict(self.metadata)
            payload["clip_path"] = str(outside)
            self.metadata_path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(list_clip_candidates(self.root), [])
        finally:
            outside.unlink(missing_ok=True)

    def test_invalid_review_state_is_rejected(self):
        item = list_clip_candidates(self.root)[0]
        with self.assertRaises(ValueError):
            update_clip_review_status(item, "published")

    def test_number_value_handles_bad_metadata(self):
        self.assertEqual(number_value("not-a-number"), 0.0)
        self.assertEqual(number_value("3.5"), 3.5)


if __name__ == "__main__":
    unittest.main()
