import tempfile
import unittest
from pathlib import Path

from gta_researcher.storage import ResearchStore


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = ResearchStore(Path(self.temp_dir.name) / "test.db")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_default_sources_are_seeded(self):
        self.assertGreaterEqual(len(self.store.list_sources()), 1)

    def test_source_add_and_toggle(self):
        source_id = self.store.add_source(
            "Test feed", "https://example.com/feed.xml", "rss", "Test source"
        )
        self.assertIsNotNone(source_id)
        self.store.set_source_active(source_id, False)
        source = next(item for item in self.store.list_sources() if item["id"] == source_id)
        self.assertEqual(source["active"], 0)

    def test_article_and_discovery_round_trip(self):
        source = self.store.list_sources()[0]
        article_id, inserted = self.store.save_article({
            "source_id": source["id"],
            "url": "https://example.com/gta-vi-story",
            "title": "GTA VI story",
            "domain": "example.com",
            "summary": "Summary",
            "content": "Article content",
            "published_at": "",
        })
        self.assertTrue(inserted)
        self.store.add_discovery(article_id, {
            "fingerprint": "fp-one",
            "title": "A GTA VI discovery",
            "claim": "A gameplay detail.",
            "script": "Here is the script.",
            "hashtags": ["#GTAVI"],
            "overall_score": 7.5,
        })
        items = self.store.list_discoveries()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["hashtags"], ["#GTAVI"])
        self.assertEqual(items[0]["source_url"], "https://example.com/gta-vi-story")

    def test_similar_titles_are_not_suppressed(self):
        source = self.store.list_sources()[0]
        article_one, _ = self.store.save_article({
            "source_id": source["id"], "url": "https://example.com/a",
            "title": "Article A", "content": "x",
        })
        article_two, _ = self.store.save_article({
            "source_id": source["id"], "url": "https://example.com/b",
            "title": "Article B", "content": "y",
        })
        for article_id, fp in ((article_one, "one"), (article_two, "two")):
            self.store.add_discovery(article_id, {
                "fingerprint": fp, "title": "Same story title",
                "claim": "Same claim", "overall_score": 8,
            })
        self.assertEqual(len(self.store.list_discoveries()), 2)


if __name__ == "__main__":
    unittest.main()
