import tempfile
import unittest
from pathlib import Path

from gta_researcher.pipeline import analyze_pending_articles
from gta_researcher.storage import ResearchStore


class FakeResearcher:
    def analyze_article(self, article):
        return [{
            "title": "A useful GTA VI gameplay detail",
            "category": "Gameplay mechanic",
            "claim": "The article describes a gameplay interaction.",
            "explanation": "A plain-language explanation.",
            "evidence_type": "independently_reported",
            "confidence": 80,
            "why_interesting": "It could make a useful short video.",
            "clip_angle": "Explain the mechanic in 25 seconds.",
            "series": "Things You Missed in GTA VI",
            "hook": "You might have missed this GTA VI detail.",
            "script": "Here is the short voiceover.",
            "visual_notes": "Show the relevant gameplay footage.",
            "hashtags": ["#GTAVI"],
            "novelty_score": 8,
            "shareability_score": 7,
            "visual_potential_score": 9,
        }]


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = ResearchStore(Path(self.temp_dir.name) / "pipeline.db")
        source = self.store.list_sources()[0]
        self.store.save_article({
            "source_id": source["id"],
            "url": "https://example.com/gta-vi-article",
            "title": "GTA VI article",
            "domain": "example.com",
            "summary": "A test summary",
            "content": "A test article about GTA VI gameplay.",
            "published_at": "",
        })

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_analyze_pending_article_saves_discovery(self):
        result = analyze_pending_articles(self.store, FakeResearcher())
        self.assertEqual(result.articles_analyzed, 1)
        self.assertEqual(result.discoveries_saved, 1)
        discoveries = self.store.list_discoveries()
        self.assertEqual(len(discoveries), 1)
        self.assertEqual(discoveries[0]["title"], "A useful GTA VI gameplay detail")
        self.assertEqual(discoveries[0]["status"], "new")


if __name__ == "__main__":
    unittest.main()
