import unittest

from gta_researcher.collectors import is_gta_relevant, normalize_url, validate_public_url


class CollectorTests(unittest.TestCase):
    def test_normalize_url_removes_tracking(self):
        self.assertEqual(
            normalize_url("https://example.com/news?utm_source=test&ref=abc#top"),
            "https://example.com/news?ref=abc",
        )

    def test_relevance_filter(self):
        self.assertTrue(is_gta_relevant("Grand Theft Auto VI gameplay details"))
        self.assertTrue(is_gta_relevant("Vice City discovery"))
        self.assertFalse(is_gta_relevant("Unrelated racing game review"))

    def test_rejects_localhost(self):
        with self.assertRaises(ValueError):
            validate_public_url("http://localhost/admin")


if __name__ == "__main__":
    unittest.main()
