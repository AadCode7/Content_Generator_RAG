from datetime import datetime, timezone
import unittest

from gta_researcher.live_clips import ChatSpikeDetector, SpikeConfig


class ChatSpikeDetectorTests(unittest.TestCase):
    def test_normal_rate_does_not_trigger(self):
        detector = ChatSpikeDetector(SpikeConfig(min_messages=5, cooldown_seconds=0))
        spikes = []
        # One message every two seconds: no ten-second bucket reaches threshold.
        for second in range(0, 120, 2):
            spikes.append(detector.add_message(float(second)))
        self.assertFalse(any(spikes))

    def test_sudden_burst_triggers(self):
        detector = ChatSpikeDetector(
            SpikeConfig(min_messages=6, ratio_threshold=2.0, cooldown_seconds=60)
        )
        for second in range(0, 600, 20):
            detector.add_message(float(second))
        spike = None
        for _ in range(8):
            spike = detector.add_message(601.0)
        self.assertIsNotNone(spike)
        self.assertEqual(spike.messages_in_bucket, 8)

    def test_cooldown_suppresses_duplicate_spikes(self):
        detector = ChatSpikeDetector(
            SpikeConfig(min_messages=2, ratio_threshold=2.0, cooldown_seconds=45)
        )
        first = detector.add_message(100.0)
        second = detector.add_message(101.0)
        self.assertIsNone(first)
        self.assertIsNotNone(second)
        self.assertIsNone(detector.add_message(102.0))

    def test_naive_datetime_is_rejected(self):
        detector = ChatSpikeDetector()
        with self.assertRaises(ValueError):
            detector.add_message(datetime(2026, 1, 1))


if __name__ == "__main__":
    unittest.main()
