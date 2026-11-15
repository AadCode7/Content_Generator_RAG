import unittest

from gta_researcher.scoring import clamp_score, fingerprint, normalize_text, score_discovery


class ScoringTests(unittest.TestCase):
    def test_scores_are_bounded(self):
        result = score_discovery({
            "novelty_score": 20,
            "shareability_score": 0,
            "visual_potential_score": 7,
            "confidence": 120,
        })
        self.assertEqual(result["novelty_score"], 10)
        self.assertEqual(result["shareability_score"], 1)
        self.assertEqual(result["confidence"], 100)
        self.assertGreaterEqual(result["overall_score"], 1)
        self.assertLessEqual(result["overall_score"], 10)

    def test_invalid_score_uses_default(self):
        self.assertEqual(clamp_score("not-a-number"), 5)

    def test_normalize_text(self):
        self.assertEqual(normalize_text("GTA VI: Vice City!"), "gta vi vice city")

    def test_fingerprint_is_stable(self):
        self.assertEqual(fingerprint("GTA VI details"), fingerprint("GTA VI details"))


if __name__ == "__main__":
    unittest.main()
