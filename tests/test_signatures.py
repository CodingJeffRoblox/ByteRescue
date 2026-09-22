import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from byterescue.recovery import signatures
import fixtures


class TestJPEG(unittest.TestCase):
    def test_uses_last_eoi_not_thumbnail_eoi(self):
        data = fixtures.jpeg_with_embedded_thumbnail() + b"TRAILING_JUNK"
        result = signatures.carve("JPEG", data, 0)
        self.assertTrue(result["verified"])
        # Must end at the REAL EOI (end of the whole blob minus the trailing junk),
        # not at the embedded thumbnail's earlier EOI.
        expected_end = len(fixtures.jpeg_with_embedded_thumbnail())
        self.assertEqual(result["end"], expected_end)


class TestPNG(unittest.TestCase):
    def test_full_png_recovered_with_iend(self):
        data = fixtures.png_bytes()
        result = signatures.carve("PNG", data, 0)
        self.assertTrue(result["verified"])
        self.assertEqual(result["end"], len(data))
        self.assertEqual(signatures.validate("PNG", data[:result["end"]], True), "passed")


class TestPDF(unittest.TestCase):
    def test_uses_last_eof_for_incremental_update(self):
        data = fixtures.pdf_with_incremental_update()
        result = signatures.carve("PDF", data, 0)
        self.assertTrue(result["verified"])
        self.assertEqual(result["end"], len(data))  # captures BOTH revisions, not just the first


class TestZIP(unittest.TestCase):
    def test_multi_entry_zip_carved_as_one_valid_archive(self):
        import zipfile
        import io as _io
        data = fixtures.multi_entry_zip()
        result = signatures.carve("ZIP", data, 0)
        self.assertTrue(result["verified"])
        self.assertEqual(result["end"], len(data))
        with zipfile.ZipFile(_io.BytesIO(data[:result["end"]])) as z:
            self.assertIsNone(z.testzip())
            self.assertEqual(set(z.namelist()), {"a.txt", "b.txt", "c/data.bin"})

    def test_docx_detected_via_ooxml_content(self):
        data = fixtures.docx_like_zip()
        ext = signatures.detect_ooxml_extension(data)
        self.assertEqual(ext, ".docx")


class TestGZIP(unittest.TestCase):
    def test_gzip_detected_unverified_but_decompresses(self):
        data = fixtures.gzip_bytes()
        result = signatures.carve("GZIP", data, 0)
        self.assertFalse(result["verified"])  # honestly unverified -- no footer exists
        self.assertEqual(signatures.validate("GZIP", data[:result["end"]], False), "passed")


class TestRIFF(unittest.TestCase):
    def test_wav_exact_size_and_extension(self):
        data = fixtures.wav_bytes()
        result = signatures.carve("RIFF", data, 0)
        self.assertTrue(result["verified"])
        self.assertEqual(result["ext"], ".wav")
        self.assertEqual(result["end"], len(data))
        self.assertEqual(signatures.validate("RIFF", data, True), "passed")


class TestSQLite(unittest.TestCase):
    def test_exact_size_from_page_size_and_count(self):
        data = fixtures.sqlite_bytes()
        result = signatures.carve("SQLITE", data, 0)
        self.assertTrue(result["verified"])
        self.assertEqual(result["end"], len(data))


class TestBMP(unittest.TestCase):
    def test_valid_bmp_accepted(self):
        data = fixtures.bmp_bytes()
        result = signatures.carve("BMP", data, 0)
        self.assertTrue(result["verified"])
        self.assertEqual(result["end"], len(data))

    def test_bare_bm_bytes_rejected_as_false_positive(self):
        # "BM" followed by plausible-looking but structurally wrong data
        # should be rejected outright, not carved as a guess.
        junk = b"BM" + os.urandom(40)
        result = signatures.carve("BMP", junk, 0)
        self.assertIsNone(result)


class TestPE(unittest.TestCase):
    def test_valid_pe_end_from_section_table(self):
        data = fixtures.pe_bytes()
        result = signatures.carve("PE", data, 0)
        self.assertIsNotNone(result)
        self.assertTrue(result["verified"])
        self.assertEqual(result["end"], len(data))

    def test_bare_mz_without_pe_header_rejected(self):
        junk = b"MZ" + os.urandom(200)
        result = signatures.carve("PE", junk, 0)
        self.assertIsNone(result)


class TestELF(unittest.TestCase):
    def test_valid_elf64_end_from_section_headers(self):
        data = fixtures.elf64_bytes()
        result = signatures.carve("ELF", data, 0)
        self.assertIsNotNone(result)
        self.assertTrue(result["verified"])
        self.assertEqual(result["end"], len(data))


class TestMP4(unittest.TestCase):
    def test_box_walk_covers_all_boxes(self):
        data = fixtures.mp4_bytes()
        ftyp_idx = data.find(b"ftyp")
        result = signatures.carve("MP4", data, ftyp_idx)
        self.assertIsNotNone(result)
        self.assertTrue(result["verified"])
        self.assertEqual(result["end"], len(data))


class TestNoFalsePositiveSignaturesInSpecs(unittest.TestCase):
    def test_no_single_byte_or_range_headers(self):
        for name, spec in signatures.SIGNATURES.items():
            headers = spec["header"]
            if isinstance(headers, bytes):
                headers = (headers,)
            for h in headers:
                self.assertGreaterEqual(len(h), 2, f"{name} header {h!r} too short to be a safe magic")


if __name__ == "__main__":
    unittest.main()
