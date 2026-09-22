import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from byterescue.recovery import text_recovery
import fixtures


class TestTextDetection(unittest.TestCase):
    def test_ascii_detected(self):
        data = fixtures.ascii_text()
        cands = text_recovery.find_candidates(data, min_length=40)
        self.assertTrue(any(c["encoding"] == "ASCII" for c in cands))
        c = next(c for c in cands if c["encoding"] == "ASCII")
        self.assertGreaterEqual(c["confidence"], 0.55)

    def test_utf8_with_accents_detected(self):
        data = fixtures.utf8_text()
        cands = text_recovery.find_candidates(data, min_length=40)
        self.assertTrue(any(c["encoding"] == "UTF-8" for c in cands))

    def test_utf16le_detected(self):
        data = fixtures.utf16le_text()
        cands = text_recovery.find_candidates(data, min_length=40)
        self.assertTrue(any(c["encoding"] == "UTF-16 LE" for c in cands))

    def test_utf16be_detected(self):
        data = fixtures.utf16be_text()
        cands = text_recovery.find_candidates(data, min_length=40)
        self.assertTrue(any(c["encoding"] == "UTF-16 BE" for c in cands))

    def test_random_binary_rejected(self):
        data = os.urandom(4000)
        cands = text_recovery.find_candidates(data, min_length=40)
        self.assertEqual(cands, [])

    def test_preview_matches_original_text(self):
        data = fixtures.ascii_text()
        cands = text_recovery.find_candidates(data, min_length=40)
        preview = text_recovery.preview_text(cands[0])
        self.assertIn("Hello Daniel", preview)

    def test_short_runs_below_min_length_not_reported(self):
        data = b"\x00\x01Hi\x02\x03" + os.urandom(50)
        cands = text_recovery.find_candidates(data, min_length=200)
        self.assertEqual(cands, [])


if __name__ == "__main__":
    unittest.main()
