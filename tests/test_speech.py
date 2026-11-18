import io
import unittest
import wave

from gta_researcher.speech import (
    DEFAULT_VOICE,
    DEFAULT_RATE,
    DEFAULT_PITCH,
    VOICE_OPTIONS,
    VOICE_PROFILE_NAME,
    VOICE_PROFILE_DESCRIPTION,
    MIN_VOICEOVER_WORDS,
    VOICEOVER_WORDS_PER_MINUTE,
    compose_voiceover_text,
    count_words,
    estimate_duration_seconds,
    pcm_to_wav,
)


class SpeechTests(unittest.TestCase):
    def test_default_voice_is_conversational_radio_presenter(self):
        self.assertEqual(DEFAULT_VOICE, "en-GB-LibbyNeural")
        self.assertEqual(DEFAULT_RATE, "+8%")
        self.assertEqual(DEFAULT_PITCH, "-1Hz")
        self.assertEqual(
            VOICE_PROFILE_NAME,
            "Conversational British female radio voice",
        )
        self.assertIn("British female", VOICE_PROFILE_DESCRIPTION)
        self.assertIn("en-US-JennyNeural", VOICE_OPTIONS.values())
        self.assertIn("en-GB-MaisieNeural", VOICE_OPTIONS.values())

    def test_compose_voiceover_adds_hook_once(self):
        hook = "Wait until you notice this detail."
        body = "Rockstar may have hidden more than you think."
        self.assertEqual(
            compose_voiceover_text(hook, body),
            f"{hook}\n\n{body}",
        )
        self.assertEqual(
            compose_voiceover_text(hook, f"{hook}\n\n{body}"),
            f"{hook}\n\n{body}",
        )

    def test_word_count_and_duration_estimate(self):
        script = " ".join(f"word{i}" for i in range(MIN_VOICEOVER_WORDS))
        self.assertEqual(count_words(script), MIN_VOICEOVER_WORDS)
        self.assertEqual(VOICEOVER_WORDS_PER_MINUTE, 175)
        self.assertGreaterEqual(estimate_duration_seconds(script), 60)

    def test_pcm_to_wav_creates_valid_mono_pcm_wav(self):
        pcm = b"\x00\x00\x01\x00\xff\x7f\x00\x80"
        wav_bytes = pcm_to_wav(pcm, sample_rate=24_000, channels=1, sample_width=2)
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
            self.assertEqual(wav_file.getnchannels(), 1)
            self.assertEqual(wav_file.getsampwidth(), 2)
            self.assertEqual(wav_file.getframerate(), 24_000)
            self.assertEqual(wav_file.getnframes(), 4)
            self.assertEqual(wav_file.readframes(4), pcm)

    def test_pcm_to_wav_rejects_empty_or_unaligned_audio(self):
        with self.assertRaises(ValueError):
            pcm_to_wav(b"")
        with self.assertRaises(ValueError):
            pcm_to_wav(b"\x00", channels=1, sample_width=2)


if __name__ == "__main__":
    unittest.main()
