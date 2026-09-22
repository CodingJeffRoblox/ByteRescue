"""GUI-level regression tests for RecoveryCenter's results-table syncing.

Unlike the other test modules, these instantiate real Tkinter widgets (a
real ByteRescue root + RecoveryCenter), since the bugs these guard against
only exist in the GUI-wiring code, not in the recovery engine itself.
Requires a display, same as running the app.

All classes in this file share ONE ByteRescue root, created in
setUpModule()/torn down in tearDownModule(), rather than each creating its
own tk.Tk(). Multiple simultaneous Tk() roots in one process is a known
soft spot in Tkinter itself (not an application bug) -- in testing this
produced stray "main thread is not in main loop" / "invalid command name"
errors purely from one test class's leftover state bleeding into the
next's mainloop(), which a single shared root avoids entirely and also
better matches how ByteRescue is actually used (one window per process).
"""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import byterescue.app as app_module

ROOT = None


def setUpModule():
    global ROOT
    ROOT = app_module.ByteRescue()
    _pump(ROOT, lambda: hasattr(ROOT, "buttons") and ROOT.state() != "withdrawn", timeout_s=15)


def tearDownModule():
    global ROOT
    if ROOT is not None:
        ROOT.destroy()
        ROOT = None


def _pump(root, predicate, timeout_s=15):
    """Block (via a real mainloop(), not manual .update() polling) until
    `predicate()` is true or timeout_s elapses. A real mainloop is required
    here, not optional polish: ByteRescue's startup and RecoveryScan both
    call `after()` from a background thread, which Tkinter only allows
    while the main thread is genuinely inside mainloop() -- doing this with
    .update() calls instead raises "main thread is not in main loop"."""
    deadline = time.monotonic() + timeout_s
    state = {"ok": False}

    def check():
        if predicate():
            state["ok"] = True
            root.quit()
            return
        if time.monotonic() >= deadline:
            root.quit()
            return
        root.after(15, check)

    root.after(15, check)
    root.mainloop()  # returns once check() calls quit(); does not destroy the window
    return state["ok"]


class _FakeScan:
    """Minimal stand-in for RecoveryScan -- just what _sync_results reads."""
    rejected = 0

    def __init__(self, results):
        self.results = results


def _make_item(offset, malformed=False):
    return {
        "type": "PNG", "extension": ".png", "size": 1024,
        # A float offset can't go through f"0x{...:X}" -- this is the
        # simplest realistic stand-in for "some item field has an
        # unexpected type", the actual trigger class for the bug below.
        "offset": (float(offset) if malformed else offset),
        "confidence": "High", "validation": "passed", "status": "Likely complete",
    }


@unittest.skipUnless(os.name == "nt", "GUI tests require a Windows display")
class TestResultsSyncSurvivesOneBadItem(unittest.TestCase):
    """Regression test for a real bug: one malformed result item used to
    permanently break the results table. _sync_results() had no per-item
    error handling, and only advanced its `_row_count` bookmark AFTER the
    whole batch succeeded -- so a single bad item mid-batch would (a) abort
    that sync with the bookmark left pointing at an EARLIER, already-
    inserted row, and (b) every later sync attempt would then immediately
    crash retrying that same already-inserted row (Tkinter raises on a
    duplicate Treeview item id), permanently capping the visible table
    with no further rows ever appearing -- while the scan's own summary
    counts (computed separately, not gated on the table sync succeeding)
    kept reporting the true, larger count. That mismatch -- a confident
    "Found: N" next to a table that stopped updating -- is exactly what
    was reported in production.
    """

    def _new_recovery_center(self):
        rc = app_module.RecoveryCenter(ROOT)
        self.addCleanup(rc.destroy)
        return rc

    def test_all_other_items_still_render_when_one_item_is_malformed(self):
        rc = self._new_recovery_center()
        items = [_make_item(0x100 + i * 0x10, malformed=(i == 5)) for i in range(9)]
        rc.scan = _FakeScan(items)
        rc._row_count = 0

        rc._sync_results()

        # The bookmark must reach the end -- no permanent retry-loop stall.
        self.assertEqual(rc._row_count, len(items))
        # Every item except the one deliberately-malformed one should have
        # a real row; losing that one row is an acceptable, logged
        # trade-off, but it must never take the rest of the table with it.
        self.assertEqual(len(rc.tree.get_children()), len(items) - 1)

    def test_results_batches_across_multiple_sync_calls_do_not_duplicate_or_stall(self):
        # Mirrors real usage: _sync_results() is called repeatedly as a scan
        # progresses (throttled progress ticks), not just once at the end.
        rc = self._new_recovery_center()
        all_items = [_make_item(0x1000 + i * 0x20) for i in range(20)]

        rc.scan = _FakeScan(all_items[:6])
        rc._row_count = 0
        rc._sync_results()
        self.assertEqual(len(rc.tree.get_children()), 6)

        rc.scan.results = all_items[:14]
        rc._sync_results()
        self.assertEqual(len(rc.tree.get_children()), 14)

        rc.scan.results = all_items
        rc._sync_results()
        self.assertEqual(len(rc.tree.get_children()), 20)
        self.assertEqual(rc._row_count, 20)

    def test_summary_label_reflects_full_scan_results_not_just_rendered_rows(self):
        rc = self._new_recovery_center()
        items = [_make_item(0x100 + i, malformed=(i == 2)) for i in range(5)]
        rc.scan = _FakeScan(items)
        rc._row_count = 0

        rc._sync_results()

        # The summary line is computed from scan.results directly, so it
        # must count all 5 even though only 4 rows are actually visible --
        # this is correct/intended, but it's also exactly why a silent
        # table stall was so confusing: the header line looked right.
        self.assertIn("Found: 5", rc.summary_var.get())
        self.assertEqual(len(rc.tree.get_children()), 4)


@unittest.skipUnless(os.name == "nt", "GUI tests require a Windows display")
class TestStartScanCanRunTwice(unittest.TestCase):
    """Regression test for a real bug: _start_scan()'s re-entry guard
    checked `self.scan is not None`, but self.scan is intentionally never
    reset to None after a scan finishes (Preview/Recover Selected/Export
    Report/View in Hex Viewer all need it to keep pointing at the last
    completed scan's results). That meant the guard was permanently true
    after the very first scan ever run in a given Recovery Center window --
    clicking START RECOVERY SCAN a second time did nothing at all, with no
    error and no feedback. Fixed with a separate `_scan_running` flag.
    """

    def _pump_until(self, predicate, timeout_s=15):
        return _pump(ROOT, predicate, timeout_s)

    def test_second_scan_starts_after_first_completes(self):
        import tempfile
        from pathlib import Path
        from tkinter import messagebox

        original_askyesno = messagebox.askyesno
        messagebox.askyesno = lambda *a, **k: True
        self.addCleanup(lambda: setattr(messagebox, "askyesno", original_askyesno))

        # ignore_cleanup_errors: Windows can be slow to release a just-closed
        # file handle (AV scanning, GC timing) -- an OS/test-process quirk,
        # not evidence this test's own assertions (already made by the time
        # cleanup runs) are wrong.
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            src = Path(d) / "blob.bin"
            src.write_bytes(
                b"\x89PNG\r\n\x1a\n" + b"\x00" * 30 + b"IEND\xaeB`\x82" + b"\x00" * 2000
            )
            dest = Path(d) / "out"
            dest.mkdir()

            rc = app_module.RecoveryCenter(ROOT)
            self.addCleanup(rc.destroy)
            rc._chosen_file_path = src
            rc.source_path_var.set(str(src))
            rc.dest_var.set(str(dest))
            rc.mode_var.set(app_module.MODE_SIGNATURE)
            rc._on_mode_change()
            rc._set_all_formats(False)
            rc.format_vars["PNG"].set(True)

            rc._start_scan()
            self.assertTrue(self._pump_until(lambda: rc.last_log is not None),
                             "first scan never finished")
            self.assertEqual(rc.last_log["status"], "complete")
            first_scan_obj = rc.scan
            self.assertIsNotNone(first_scan_obj, "self.scan must stay set so Recover Selected etc still work")
            self.assertFalse(rc._scan_running)

            rc.tree.delete(*rc.tree.get_children())
            rc.last_log = None
            rc._start_scan()  # exactly what clicking the button does a second time

            self.assertTrue(self._pump_until(lambda: rc.last_log is not None),
                             "second scan never started/finished -- START RECOVERY SCAN is stuck")
            self.assertIsNot(rc.scan, first_scan_obj, "a new scan should have been created")
            self.assertEqual(len(rc.tree.get_children()), 1, "second scan should have populated results again")


if __name__ == "__main__":
    unittest.main()
