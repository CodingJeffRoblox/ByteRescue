import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from byterescue.recovery import filesystem
import fixtures


class _BytesReader:
    """Same read_at(offset, length) interface as RandomAccessSource, backed
    by an in-memory buffer instead of a real file -- keeps these tests fast
    and avoids touching disk."""

    def __init__(self, data):
        self._data = data

    def read_at(self, offset, length):
        return self._data[offset:offset + length]


def _by_path(entries, path):
    matches = [e for e in entries if e["path"] == path]
    assert matches, f"{path!r} not found among {[e['path'] for e in entries]}"
    return matches[0]


class TestFAT16(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image, cls.expected = fixtures.build_fat16_image()
        cls.reader = _BytesReader(cls.image)
        cls.bpb = filesystem.probe(cls.reader)

    def test_probe_classifies_as_fat16(self):
        self.assertIsNotNone(self.bpb)
        self.assertEqual(self.bpb["fat_type"], "FAT16")

    def test_normal_single_cluster_file(self):
        entries = filesystem.walk(self.reader, self.bpb)
        e = _by_path(entries, "HELLO.TXT")
        self.assertFalse(e["deleted"])
        data, verified = filesystem.read_entry_bytes(self.reader, self.bpb, e)
        self.assertTrue(verified)  # real FAT chain followed (trivial 1-cluster case)
        self.assertEqual(data, self.expected["hello_content"])

    def test_normal_multi_cluster_file_follows_real_chain(self):
        entries = filesystem.walk(self.reader, self.bpb)
        e = _by_path(entries, "BIG.BIN")
        data, verified = filesystem.read_entry_bytes(self.reader, self.bpb, e)
        self.assertTrue(verified)
        self.assertEqual(data, self.expected["big_content"])
        self.assertEqual(len(data), 600)  # spans 2 clusters, confirms real chain-following

    def test_deleted_file_recovered_via_contiguous_assumption(self):
        entries = filesystem.walk(self.reader, self.bpb)
        e = _by_path(entries, "?ELETED.TXT")  # lost first char, marked with '?'
        self.assertTrue(e["deleted"])
        data, verified = filesystem.read_entry_bytes(self.reader, self.bpb, e)
        self.assertFalse(verified)  # contiguous ASSUMED, not proven -- must say so
        self.assertEqual(data, self.expected["deleted_content"])

    def test_subdirectory_recursion_and_dot_entries_skipped(self):
        entries = filesystem.walk(self.reader, self.bpb)
        paths = [e["path"] for e in entries]
        self.assertIn("SUBDIR", paths)
        self.assertIn("SUBDIR/NESTED.TXT", paths)
        self.assertNotIn("SUBDIR/.", paths)
        self.assertNotIn("SUBDIR/..", paths)
        nested = _by_path(entries, "SUBDIR/NESTED.TXT")
        data, verified = filesystem.read_entry_bytes(self.reader, self.bpb, nested)
        self.assertTrue(verified)
        self.assertEqual(data, self.expected["nested_content"])

    def test_long_filename_reconstructed_from_vfat_entries(self):
        entries = filesystem.walk(self.reader, self.bpb)
        paths = [e["path"] for e in entries]
        self.assertIn(self.expected["long_name"], paths)


class TestFAT32(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image, cls.expected = fixtures.build_fat32_image()
        cls.reader = _BytesReader(cls.image)
        cls.bpb = filesystem.probe(cls.reader)

    def test_probe_classifies_as_fat32(self):
        self.assertIsNotNone(self.bpb)
        self.assertEqual(self.bpb["fat_type"], "FAT32")

    def test_root_is_a_cluster_chain_not_a_fixed_region(self):
        entries = filesystem.walk(self.reader, self.bpb)
        paths = [e["path"] for e in entries]
        self.assertIn("ROOTFILE.TXT", paths)
        self.assertNotIn(".", paths)
        self.assertNotIn("..", paths)

    def test_file_content_via_32bit_fat_entries(self):
        entries = filesystem.walk(self.reader, self.bpb)
        e = _by_path(entries, "ROOTFILE.TXT")
        data, verified = filesystem.read_entry_bytes(self.reader, self.bpb, e)
        self.assertTrue(verified)
        self.assertEqual(data, self.expected["file_content"])


class TestProbeRejectsNonFat(unittest.TestCase):
    def test_random_bytes_rejected(self):
        self.assertIsNone(filesystem.probe(_BytesReader(os.urandom(4096))))

    def test_all_zero_boot_sector_rejected(self):
        self.assertIsNone(filesystem.probe(_BytesReader(b"\x00" * 512)))

    def test_short_buffer_rejected(self):
        self.assertIsNone(filesystem.probe(_BytesReader(b"\x55\xAA")))


class TestRandomAccessSource(unittest.TestCase):
    def test_reads_arbitrary_offsets_from_a_real_file(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "img.bin"
            p.write_bytes(b"0123456789" * 100)
            with filesystem.RandomAccessSource(p) as src:
                self.assertEqual(src.read_at(0, 10), b"0123456789")
                self.assertEqual(src.read_at(500, 5), b"01234")


if __name__ == "__main__":
    unittest.main()
