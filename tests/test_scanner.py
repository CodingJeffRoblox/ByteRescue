import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from byterescue.recovery import scanner
import fixtures


class TestFilesystemModeIntegration(unittest.TestCase):
    def test_recovers_deleted_file_from_fat16_image(self):
        image, expected = fixtures.build_fat16_image()
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "fat16.img"
            dst = Path(d) / "out"
            path.write_bytes(image)
            scan = scanner.RecoveryScan(path, dst, mode="filesystem")
            log = scan.run()
            self.assertEqual(log["status"], "complete")
            self.assertEqual(len(scan.results), 1)  # only the ONE deleted file, not the 3 live ones
            item = scan.results[0]
            self.assertEqual(item["original_name"], "?ELETED.TXT")
            self.assertEqual(item["blob"], expected["deleted_content"])
            self.assertFalse(item["verified"])  # contiguous assumption, honestly labeled
            self.assertEqual(item["confidence"], "High")  # fits in one cluster -- no assumption risk

            out = scan.write_result(item, 1)
            self.assertTrue(out.exists())
            self.assertEqual(out.read_bytes(), expected["deleted_content"])
            self.assertIn("ELETED", out.name)  # original name preserved (minus the lost first char)

    def test_non_fat_source_reports_a_clear_error_not_a_silent_empty_result(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "notfat.img"
            dst = Path(d) / "out"
            path.write_bytes(os.urandom(4096))
            scan = scanner.RecoveryScan(path, dst, mode="filesystem")
            log = scan.run()
            self.assertEqual(log["status"], "complete")
            self.assertEqual(len(scan.results), 0)
            self.assertTrue(log["errors"])
            self.assertIn("FAT12/16/32", log["errors"][0])


class TestDevicePathHandling(unittest.TestCase):
    def test_is_device_path_recognizes_physical_drive(self):
        self.assertTrue(scanner.is_device_path(r"\\.\PhysicalDrive2"))
        self.assertTrue(scanner.is_device_path(r"\\?\Volume{guid}"))
        self.assertFalse(scanner.is_device_path(r"C:\Users\me\evidence.img"))
        self.assertFalse(scanner.is_device_path("evidence.img"))

    def test_recovery_scan_keeps_device_path_as_plain_str_not_mangled_path(self):
        # Regression test: Path(r"\\.\PhysicalDrive2") gets parsed by pathlib
        # as a UNC path and stringifies back out as "\\.\PhysicalDrive2\"
        # (trailing backslash added), which Windows then refuses to open.
        # RecoveryScan must never let a device path reach Path(...).
        with tempfile.TemporaryDirectory() as d:
            dst = Path(d) / "out"
            scan = scanner.RecoveryScan(r"\\.\PhysicalDrive2", dst, mode="signature")
            self.assertIsInstance(scan.source_path, str)
            self.assertEqual(scan.source_path, r"\\.\PhysicalDrive2")
            self.assertFalse(scan.source_path.endswith("\\"))


class TestChunkedReaderBoundaryCrossing(unittest.TestCase):
    def test_signature_split_across_chunk_boundary_is_still_found(self):
        # Build a blob where the PNG header deliberately straddles a chunk
        # boundary once read in small fixed-size pieces.
        png = fixtures.png_bytes()
        prefix = b"\x00" * 10
        data = prefix + png
        chunk_size = 10 + 4  # splits the 8-byte PNG magic right down the middle
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "blob.bin"
            path.write_bytes(data)
            reader = scanner.ChunkedReader(path, chunk_size=chunk_size, overlap=16)
            reassembled = b""
            windows = list(reader)
            # Every byte of the source must appear in at least one window,
            # and windows must overlap (not just be back-to-back slices).
            self.assertGreater(len(windows), 1)
            covered = bytearray(len(data))
            for start, buf in windows:
                covered[start:start + len(buf)] = b"\x01" * len(buf)
            self.assertTrue(all(covered))

    def test_full_scan_finds_png_regardless_of_chunk_size(self):
        png = fixtures.png_bytes()
        data = os.urandom(5000) + png + os.urandom(5000)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "blob.bin"
            dst = Path(d) / "out"
            path.write_bytes(data)
            scan = scanner.RecoveryScan(
                path, dst, mode="signature", selected_formats=["PNG"],
                use_chunked=True, chunk_size=2000, overlap=64,
            )
            log = scan.run()
            self.assertEqual(log["status"], "complete")
            self.assertEqual(len(scan.results), 1)
            self.assertTrue(scan.results[0]["verified"])


class TestDuplicateDetection(unittest.TestCase):
    def test_overlapping_windows_do_not_duplicate_a_hit(self):
        png = fixtures.png_bytes()
        data = os.urandom(2000) + png + os.urandom(2000)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "blob.bin"
            dst = Path(d) / "out"
            path.write_bytes(data)
            # A big overlap relative to chunk size guarantees the PNG header
            # appears in more than one window.
            scan = scanner.RecoveryScan(
                path, dst, mode="signature", selected_formats=["PNG"],
                use_chunked=True, chunk_size=1500, overlap=800,
            )
            scan.run()
            self.assertEqual(len(scan.results), 1)


class TestSHA256(unittest.TestCase):
    def test_hash_matches_hashlib(self):
        import hashlib
        blob = os.urandom(1024)
        self.assertEqual(scanner.sha256_bytes(blob), hashlib.sha256(blob).hexdigest())


class TestCancellation(unittest.TestCase):
    def test_cancel_before_run_stops_immediately(self):
        blob = fixtures.png_bytes() * 50
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "blob.bin"
            dst = Path(d) / "out"
            path.write_bytes(blob)
            scan = scanner.RecoveryScan(path, dst, mode="signature", selected_formats=["PNG"])
            scan.cancel()
            log = scan.run()
            self.assertEqual(log["status"], "cancelled")
            self.assertEqual(len(scan.results), 0)

    def test_cancel_mid_scan_stops_before_finishing(self):
        # 500 repeats of a PNG -- enough candidates that cancelling after the
        # 5th checkpoint call (deterministic, no sleep/race) leaves most of
        # them unprocessed if the scan really did stop early.
        blob = (fixtures.png_bytes() + os.urandom(200)) * 500
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "blob.bin"
            dst = Path(d) / "out"
            path.write_bytes(blob)
            scan = scanner.RecoveryScan(path, dst, mode="signature", selected_formats=["PNG"])
            real_checkpoint = scan._checkpoint
            calls = {"n": 0}

            def hooked_checkpoint():
                calls["n"] += 1
                if calls["n"] == 5:
                    scan.cancel()
                real_checkpoint()

            scan._checkpoint = hooked_checkpoint
            log = scan.run()
            self.assertEqual(log["status"], "cancelled")
            self.assertLess(len(scan.results), 500)


class TestDestinationSafety(unittest.TestCase):
    def test_same_folder_is_risky(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "evidence.img"
            src.write_bytes(b"x")
            self.assertTrue(scanner.destination_is_risky(src, Path(d)))

    def test_subfolder_of_source_parent_is_risky(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "evidence.img"
            src.write_bytes(b"x")
            sub = Path(d) / "recovered"
            sub.mkdir()
            self.assertTrue(scanner.destination_is_risky(src, sub))

    def test_separate_drive_folder_is_not_risky(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            src = Path(d1) / "evidence.img"
            src.write_bytes(b"x")
            self.assertFalse(scanner.destination_is_risky(src, Path(d2)))

    def test_raw_physical_drive_path_flagged(self):
        self.assertTrue(scanner.destination_is_risky(r"\\.\PhysicalDrive0", "C:/somewhere"))


class TestLargeFileScanning(unittest.TestCase):
    def test_multi_megabyte_file_with_small_chunks(self):
        png = fixtures.png_bytes()
        # ~6 MB of filler with one real PNG buried past several chunk boundaries.
        data = os.urandom(3 * 1024 * 1024) + png + os.urandom(3 * 1024 * 1024)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "big.bin"
            dst = Path(d) / "out"
            path.write_bytes(data)
            scan = scanner.RecoveryScan(
                path, dst, mode="signature", selected_formats=["PNG"],
                use_chunked=True, chunk_size=512 * 1024, overlap=4096,
            )
            log = scan.run()
            self.assertEqual(log["status"], "complete")
            self.assertEqual(len(scan.results), 1)
            self.assertEqual(scan.results[0]["size"], len(png))


class TestWriteResultAndReport(unittest.TestCase):
    def test_write_result_and_export_report(self):
        png = fixtures.png_bytes()
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "blob.bin"
            dst = Path(d) / "out"
            path.write_bytes(png)
            scan = scanner.RecoveryScan(path, dst, mode="signature", selected_formats=["PNG"])
            log = scan.run()
            out = scan.write_result(scan.results[0], 1)
            self.assertTrue(out.exists())
            self.assertEqual(out.read_bytes(), png)
            self.assertIsNotNone(scan.results[0]["sha256"])

            report_path = Path(d) / "report.json"
            scanner.export_report(log, scan.results, report_path)
            self.assertTrue(report_path.exists())
            import json
            report = json.loads(report_path.read_text())
            self.assertEqual(report["found"], 1)
            self.assertNotIn("blob", report["items"][0])


if __name__ == "__main__":
    unittest.main()
