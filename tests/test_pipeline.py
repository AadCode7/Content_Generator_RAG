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
        self.assertTrue(
            discoveries[0]["script"].startswith(discoveries[0]["hook"]),
            "The opening hook must be part of the spoken voiceover.",
        )

    def test_failed_analysis_can_be_retried_and_recovers(self):
        class BrokenResearcher:
            def analyze_article(self, article):
                raise RuntimeError("Groq rate limit exceeded")

        first_result = analyze_pending_articles(self.store, BrokenResearcher())
        self.assertEqual(first_result.articles_analyzed, 0)
        self.assertEqual(len(first_result.errors), 1)
        self.assertIn("Groq rate limit exceeded", first_result.errors[0])

        failed_articles = self.store.list_failed_articles()
        self.assertEqual(len(failed_articles), 1)
        self.assertIn("Groq rate limit exceeded", failed_articles[0]["ai_error"])

        retry_result = analyze_pending_articles(self.store, FakeResearcher())
        self.assertEqual(retry_result.articles_analyzed, 1)
        self.assertEqual(retry_result.discoveries_saved, 1)
        self.assertEqual(self.store.list_failed_articles(), [])
        self.assertEqual(
            self.store.article_status_counts(),
            {"pending": 0, "failed": 0, "processed": 1},
        )


if __name__ == "__main__":
    unittest.main()
