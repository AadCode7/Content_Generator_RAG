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
            "player_takeaway": "Use cover before crossing an exposed area.",
            "caption": "Rockstar changed the way this encounter plays out.",
            "description": "A new detail could change how players approach this situation.",
            "mentions": ["@rockstargames"],
            "hashtags": ["#GTAVI", "#GTA6"],
            "overall_score": 7.5,
        })
        items = self.store.list_discoveries()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["hashtags"], ["#GTAVI", "#GTA6"])
        self.assertEqual(
            items[0]["caption"],
            "Rockstar changed the way this encounter plays out.",
        )
        self.assertEqual(
            items[0]["description"],
            "A new detail could change how players approach this situation.",
        )
        self.assertEqual(items[0]["mentions"], ["@rockstargames"])
        self.assertEqual(
            items[0]["player_takeaway"],
            "Use cover before crossing an exposed area.",
        )
        self.assertEqual(items[0]["source_url"], "https://example.com/gta-vi-story")
        self.store.update_discovery_publish_copy(
            items[0]["id"],
            "Updated caption",
            "Updated description",
            ["@RockstarGames", "@gta"],
            ["#GTAVI"],
        )
        updated = self.store.get_discovery(items[0]["id"])
        self.assertEqual(updated["caption"], "Updated caption")
        self.assertEqual(updated["description"], "Updated description")
        self.assertEqual(updated["mentions"], ["@RockstarGames", "@gta"])
        self.assertEqual(updated["hashtags"], ["#GTAVI"])

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

    def test_player_takeaway_column_migrates_existing_database(self):
        # Simulate a database created before the player_takeaway column existed.
        with self.store.connect() as connection:
            for column_name in (
                "player_takeaway",
                "caption",
                "description",
                "mentions_json",
            ):
                connection.execute(
                    f"ALTER TABLE discoveries DROP COLUMN {column_name}"
                )

        upgraded_store = ResearchStore(self.store.database_path)
        with upgraded_store.connect() as connection:
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(discoveries)").fetchall()
            }
        self.assertIn("player_takeaway", columns)
        self.assertIn("caption", columns)
        self.assertIn("description", columns)
        self.assertIn("mentions_json", columns)

    def test_article_status_counts_and_failed_article_details(self):
        source = self.store.list_sources()[0]
        article_ids = {}
        for name, url in (
            ("Pending article", "https://example.com/pending"),
            ("Failed article", "https://example.com/failed"),
            ("Processed article", "https://example.com/processed"),
        ):
            article_ids[name], _ = self.store.save_article({
                "source_id": source["id"],
                "url": url,
                "title": name,
                "content": "GTA VI article content",
            })

        self.store.set_article_ai_status(
            article_ids["Failed article"], "failed", "Groq rate limit exceeded"
        )
        self.store.set_article_ai_status(article_ids["Processed article"], "processed")

        self.assertEqual(
            self.store.article_status_counts(),
            {"pending": 1, "failed": 1, "processed": 1},
        )
        failed = self.store.list_failed_articles()
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["title"], "Failed article")
        self.assertEqual(failed[0]["source_name"], source["name"])
        self.assertEqual(failed[0]["ai_error"], "Groq rate limit exceeded")


if __name__ == "__main__":
    unittest.main()
