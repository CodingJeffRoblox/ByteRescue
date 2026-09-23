# Changelog

All notable changes to this project are documented here. Versions follow
[Semantic Versioning](https://semver.org/): the major.minor.patch pattern.

## 0.7.0

Repo cleanup, live debug logging, and another GUI-freeze bug caught while adding it.

### Added
- `applog.py` now also streams to the console (in addition to the existing log file) whenever ByteRescue
  is run from one -- which is the normal case, since `ByteRescue.ps1` launches it inside the elevated
  PowerShell window it opens and leaves that window open. Console output is `INFO` and up by default; set
  the `BYTERESCUE_DEBUG` environment variable to anything non-empty for a fully verbose `DEBUG` stream.
- Every run now logs its environment once at startup (ByteRescue version, Python version/executable,
  OS platform string, whether running elevated, working directory) -- exactly what would otherwise need
  to be asked for when someone reports a bug.
- New DEBUG-level log lines for previously-silent user actions in the Recovery Center: changing recovery
  mode, changing source kind, choosing a source file, choosing a destination folder, and selecting a
  drive -- so a log file from a real session now shows what the user actually clicked, not just what the
  scan engine did.

### Fixed
- **Selecting "Physical Drive" as the Recovery Center's source froze the whole window for several
  seconds** (measured 5.86s on real hardware). `_refresh_drive_list()` called `get_disks()` and
  `get_physical_disk_media_types()` directly on the GUI thread -- each shells out to a PowerShell/WMI
  subprocess -- and `_on_drive_selected()` made a *third* redundant synchronous call to
  `get_physical_disk_media_types()` on every dropdown change on top of that. This is the same class of
  bug already fixed once for the main window's drive list; this Recovery Center picker was missed at the
  time. Fixed by moving both calls to a background thread (matching the main window's existing pattern)
  and caching media types for reuse instead of re-fetching on every selection. Reproduced and confirmed
  with a new regression test (`tests/test_gui_recovery_center.py`, `TestDriveListDoesNotBlockGuiThread`)
  before and after the fix; selecting a drive source now returns in under a millisecond instead of ~6s.

### Changed
- Removed 16 stray `__pycache__/*.pyc` files that had been committed to the repo despite `.gitignore`
  already excluding them (added before the ignore rule existed, so git kept tracking them regardless).

## 0.6.1

A targeted bug hunt across every button and control in the app. Patch release: bug fixes only, no new
capability.

### Fixed
- **"START RECOVERY SCAN" became permanently dead after the first scan.** `_start_scan()`'s re-entry
  guard checked `self.scan is not None` -- but `self.scan` is intentionally never reset to `None` after
  a scan finishes (Preview/Recover Selected/Export Report/View in Hex Viewer all need it to keep
  pointing at the last completed scan's results). That made the guard permanently true after the very
  first scan ever run in a given Recovery Center window: clicking the button again did nothing at all,
  silently, with no error. Fixed with a separate `_scan_running` flag that actually tracks whether a
  scan is in flight; `self.scan` keeps its original job of holding the last scan's results. Reproduced
  and confirmed with a new regression test (`tests/test_gui_recovery_center.py`,
  `TestStartScanCanRunTwice`) before and after the fix.
- `SplashScreen._close()` destroyed its window without cancelling the pending animation's `after()` job
  -- Tkinter doesn't cancel a scheduled callback just because its target widget was destroyed, so Tcl
  would later try to fire it and raise `invalid command name ..._animate`. Minor on its own, but it also
  surfaced a deeper issue while testing: multiple independent `tk.Tk()` roots in one process (one per
  test class) is inherently fragile in Tkinter, producing spurious `RuntimeError: main thread is not in
  main loop` errors from one class's leftover state bleeding into another's `mainloop()`. The GUI test
  suite now shares a single root across all its test classes via `setUpModule`/`tearDownModule`
  (matching real usage -- ByteRescue only ever runs one window per process anyway), which fixed this at
  the root cause and, as a side effect, also made the test suite run roughly 10x faster.
- Verified (and left unchanged, since they were already correct) every other control by driving them
  through the real GUI: Open Folder, Analyze File, the main toolbar's Hex Viewer, and the Recovery
  Center's Pause/Resume/Stop/Preview/Open Log buttons.

## 0.6.0

Real logging, and a serious bug it caught: the Recovery Results table could silently stop updating
partway through a scan while the summary line kept reporting the true (larger) count.

### Added
- `byterescue/applog.py`: a real log file (`logs/byterescue.log`, rotated at 2MB) for every run.
  Previously, an exception inside a Tkinter callback was only ever printed to stderr by Tkinter's
  default handler -- invisible when launched via `ByteRescue.bat` without a console window, so an error
  could occur with literally no trace anywhere. `Tk.report_callback_exception` is now hooked to log to
  the file and show a dialog, `sys.excepthook` and `threading.excepthook` are hooked for exceptions
  outside GUI callbacks, and scan start/finish/write and results-table sync events are logged. A new
  "Open Log" button in the Recovery Center opens the file directly.

### Fixed
- **The Recovery Results table could permanently stop updating partway through a scan.**
  `_sync_results()` had no per-item error handling, and only advanced its "how far synced" bookmark
  *after* an entire batch of new rows succeeded. If any single result item's data caused
  `Treeview.insert()` to raise (e.g. an unexpected field type), the whole sync call aborted with the
  bookmark left pointing at an earlier row that was *already* inserted -- so every later sync attempt
  immediately crashed again retrying that same row (Tkinter refuses a duplicate Treeview item id),
  permanently capping the table with no further rows ever appearing. Meanwhile the summary line
  ("Found: N") is computed independently, straight from the scan's own result count, so it kept
  reporting the true, larger number -- producing exactly the symptom reported in production: a
  confident "Found: 14" next to an empty-looking table. Reproduced and confirmed with a synthetic test
  (`tests/test_gui_recovery_center.py`): the old logic capped a 9-item batch at 5 visible rows and never
  recovered; the fix (per-item try/except, logged and skipped on failure, bookmark always advances)
  correctly renders 8 of 9 real items, losing only the one genuinely bad row instead of everything after it.

## 0.5.0

Animated startup splash screen, and a real responsiveness bug fix found while building it.

### Added
- A borderless, animated loading screen (`SplashScreen` in `byterescue/app.py`) shown while the main
  window is built and the initial storage-device list is fetched. The spinner runs for as long as that
  actually takes (confirmed by test: 15+ distinct animation frames observed during a real startup), not
  a fixed fake delay -- it only enforces a small 450ms minimum so it can't flash by unnoticed on a fast
  system, and never pads out real work beyond that.

### Fixed
- `refresh_disks()` (both the initial startup fetch and the "Refresh Drives" button) ran its
  PowerShell/WMI subprocess call synchronously on the main thread, freezing the entire GUI --
  unresponsive to any input, including the splash animation during startup -- for as long as that call
  took (routinely 300ms-2s+, since PowerShell has a slow cold start). It's now backgrounded via
  `threading.Thread` with results marshaled back through `after()`, the same pattern already used for
  `RecoveryScan`, fixing the freeze in both places at once.

## 0.4.0

Launcher rewrite. `ByteRescue.bat` is now a thin shim that hands off to a new `ByteRescue.ps1`, which
does the actual work: self-elevating to Administrator, detecting Python 3.11+, installing it via winget
if it's missing, and launching the app. Minor bump: new user-facing capability (auto-elevation,
auto-install), on top of fixing launcher bugs real enough that the old batch-only launcher may not have
run at all for some users.

### Added
- **Self-elevation**: on launch, if not already running as Administrator, `ByteRescue.ps1` relaunches
  itself via a UAC prompt (`Start-Process -Verb RunAs`) and exits the non-elevated copy. A new elevated
  console window opens -- unavoidable for a script (Windows has no way to elevate a running console in
  place), so the non-elevated window explicitly says so before closing instead of just vanishing.
- **Automatic Python installation**: if no working Python 3.11+ is found, and `winget` is available, the
  launcher installs Python automatically (trying a short list of current Python.Python.3.x package IDs),
  refreshes the current session's PATH from the registry (a freshly-installed Python's PATH update isn't
  visible to an already-running process otherwise), and retries -- without requiring the window to be
  closed and reopened. If winget isn't available or the install fails, it prints the manual
  python.org download instructions instead of failing silently.
- Exit codes now propagate correctly end-to-end: if the app itself crashes, `ByteRescue.bat`'s own exit
  code reflects that instead of always reporting success.

### Fixed
Three real, independently-reproduced bugs in the previous all-batch `ByteRescue.bat`, found while
implementing the above (pure batch turned out to be a poor fit for this level of logic):
- Unescaped `|` characters in the startup banner's `echo` lines are pipe operators to `cmd.exe`, not
  literal text -- the original launcher failed with `The syntax of the command is incorrect.` and
  **halted immediately, before ever checking for Python or launching the app, on every single run.**
- `setlocal EnableExtensions EnabledDelayedExpansion` had a typo (`EnabledDelayedExpansion` isn't a real
  switch; it's `EnableDelayedExpansion`), producing `Invalid parameter to SETLOCAL command` on every run.
- The final `exit /b %errorlevel%` was meant to report whether the app actually succeeded, but `pause`
  resets `%errorlevel%` to 0 (confirmed empirically) -- so a crashed app would still make the launcher
  report success to anything checking its exit code.

These are now moot (the logic moved to `ByteRescue.ps1`, which doesn't have batch's footguns), but are
recorded here since they affected real usage of 0.1.0 through 0.3.0's launcher.

## 0.3.0

Real FAT12/16/32 filesystem-aware recovery, a Recovery Center Help/Docs tab, and a real physical-drive
bug fix found from actual hardware use. Minor bump: new capability (a fourth recovery mode with its own
engine), not just fixes.

### Added
- `byterescue/recovery/filesystem.py`: a real FAT12/16/32 reader -- boot sector/BPB parsing (Microsoft's
  own cluster-count algorithm decides FAT12 vs 16 vs 32, not the informational on-disk type string),
  8.3 and VFAT long-filename directory entries, recursive subdirectory walking, and deleted-entry recovery.
  "Recover by File System" now actually works for FAT12/16/32 sources instead of being disabled.
- Deleted-file recovery is honest about its biggest limitation: FAT deletion normally zeroes a file's
  cluster CHAIN (not just the directory entry), so a deleted file spanning more than one cluster is
  recovered by ASSUMING contiguous allocation from its known start cluster -- exactly what classic FAT
  undelete tools do, and exactly why they struggle with fragmented files. Every such result says so in
  its Status text and gets Confidence "Low" (vs "High" for a single-cluster file, where no assumption
  was needed at all).
- Recovered file names come from the real FAT/VFAT directory entry when filesystem mode finds one
  (sanitized for Windows-illegal characters) -- the first codepath in the project to actually use the
  original-filename hook `safe_output_path()` already had.
- A bonus cross-check: if filesystem-recovered bytes happen to start with a signature `signatures.py`
  already knows (JPEG, ZIP, etc.), they get run through the same structural `validate()` used elsewhere.
- Recovery Center Help/Docs tab explaining every mode, control, and results-table column in plain
  language, in the same visual style as the main window's existing help tab.
- `tests/test_filesystem.py` with hand-built, byte-exact synthetic FAT16 and FAT32 images (`tests/
  fixtures.py`) covering both FAT table formats, real multi-cluster chain-following, the deleted-file
  contiguous-allocation path, recursive subdirectories, long-filename reconstruction, and rejecting
  non-FAT sources with a clear error instead of a silent empty result.

### Fixed
- **Physical-drive scanning was fundamentally broken**: `Path(r"\\.\PhysicalDrive2")` gets parsed by
  Python's `pathlib` as a UNC path and stringifies back out as `\\.\PhysicalDrive2\` -- WITH a trailing
  backslash -- which Windows then refuses to open, raising `PermissionError` even when ByteRescue is run
  elevated. Found from a real user hitting it on real hardware. Fixed by keeping any `\\.\...` or
  `\\?\...` path a plain `str` everywhere (`recovery.scanner.is_device_path()`), never letting it reach
  `pathlib.Path()`; regression-tested in `tests/test_scanner.py`.
- A related bug the above fix surfaced: `os.stat()` on a raw device path "succeeds" but always reports
  `st_size=0` (it does not report the drive's real capacity) -- trusting that would have hit the
  scanner's "empty source, nothing to do" short-circuit and silently "completed" a scan that never read
  a single byte. Device paths (and filesystem mode) now always treat total size as unknown.
- `PermissionError` on a device-path source now includes specific, actionable guidance (confirm the
  actual elevation, check for another process holding the volume open, image the drive to a file first)
  instead of a bare "Access denied".

## 0.2.0

Recovery-engine rebuild. Minor version bump (not a patch) because this adds real new capability
(text recovery, chunked scanning, structural validation, several new signature formats) on top of
existing behavior, without breaking the public shape of the app (same executable, same GUI shell).

### Added
- Recovery Center window with four modes: Recover by Signature, Recover Text Files, Deep / Raw Scan,
  and a clearly-labeled (and disabled) Recover by File System placeholder.
- Dedicated text-recovery engine (`byterescue/recovery/text_recovery.py`): ASCII/UTF-8/UTF-16 LE/UTF-16 BE
  pattern detection with a confidence score, since plain text has no magic header to search for.
- Chunked scanning with an overlap buffer (`byterescue/recovery/scanner.py: ChunkedReader`) so a
  signature split across a chunk boundary is still found, and large sources don't need to be loaded
  into RAM or memory-mapped.
- Pause / Resume / Stop scan controls, live progress (offset, bytes scanned/total, speed, ETA,
  candidates found/valid/rejected), duplicate detection, and an exportable JSON recovery report.
- Structural validation of recovered files: Pillow for JPEG/PNG/GIF/BMP/TIFF/WEBP, `zipfile` for ZIP,
  `sqlite3` (`PRAGMA integrity_check`) for SQLite, the `wave` module for WAV, `gzip` for GZIP. Every
  result is labeled Validation: Passed / Partial / Failed / Unknown.
- New signature formats with real carving logic: BMP (size-field validated), GIF, TIFF, RAR, legacy
  Office/OLE, MKV/WebM, MP3 (ID3v2 tag detection only), Windows PE (.exe/.dll, via a validated
  DOS-header-to-PE-header-to-section-table walk), ELF (via the section header table), and MP4/MOV
  (via real ISO-BMFF box walking).
- OOXML detection: a recovered ZIP is peeked at post-carve and renamed to `.docx`/`.xlsx`/`.pptx` when
  its contents say so, instead of a fake separate "Office" signature.
- SSD/NVMe TRIM warning in the Recovery Center, using `Get-PhysicalDisk`'s MediaType (more reliable for
  this than `Win32_DiskDrive`).
- Hex Viewer integration: selecting a recovery result jumps the Hex Viewer to, and highlights, its offset.
- Destination-safety check (`scanner.destination_is_risky`) shared by the recovery flow, instead of the
  narrower same-folder-only check the old scanner had.
- Real test suite (`tests/`) with synthetic fixtures built in memory: JPEG-with-embedded-thumbnail,
  multi-revision PDF, multi-entry ZIP, a structurally real PE and ELF binary, an MP4 box tree, text
  samples in every supported encoding, and more.

### Changed
- Recovery/carving logic moved out of `app.py` into `byterescue/recovery/` (`signatures.py`,
  `text_recovery.py`, `scanner.py`), separating the recovery engine from the Tkinter GUI so it can be
  imported and tested without starting a GUI.
- ZIP carving now distinguishes Local File Header / Central Directory Header / End Of Central Directory
  and carves a multi-entry archive as one valid ZIP (verified against its real EOCD) instead of one
  broken fragment per internal entry.
- JPEG/PDF carving now searches for the LAST footer within a safety cap (not bounded by the next header
  occurrence), which correctly handles JPEGs with an embedded EXIF thumbnail and PDFs with more than one
  incremental save -- a bug found and fixed by the test suite added in this release.
- The educational `HEX_CODE_REFERENCE` dictionary moved to `byterescue/recovery/hex_reference.py`, kept
  explicitly separate from the signatures the scanner actually uses.

### Fixed
- The Hex Viewer's Search box referenced an undefined `text_widget` variable and raised `NameError` on
  every use -- it now works.
- `_scan_signatures` (the old scanner) loaded the entire source file into RAM (`data = src.read_bytes()`)
  despite a comment claiming chunked reading; replaced by `mmap`-backed scanning for files and the new
  `ChunkedReader` for chunked/raw sources.
- The main Analysis panel (`self.info`) was a plain editable `tk.Text` -- clicking into it and typing did
  nothing to the underlying data, but looked like it did. It is now `state="disabled"` (still selectable
  and copyable), matching how the Hex Viewer's own text pane already worked.
- `RecoveryScan`'s docstring/comment claimed to support a `mode="raw"` value that was never actually
  handled -- it would have silently scanned nothing. `mode` is now strictly `"signature"` or `"text"`
  (validated, raises on anything else); "Deep / Raw Scan" in the GUI is `mode="signature"` with
  `use_chunked=True`, not a third mode.

## 0.1.2

- Added the "What am I looking at?" help tab.
- Fixed a white hover/flash issue on buttons, tabs, and drive selection.
- Improved crash handling: startup errors, file errors, and recovery errors are now shown in readable
  dialogs instead of silently returning to the command prompt.
- Improved Hex Viewer: scrollbars, dark interface, larger viewing area, 128 KB preview.
- Improved recovery: prevents overwriting existing recovered files, shows scan status.

## 0.1.0

Initial release: Windows physical disk listing, folder/file analysis with SHA-256, a basic hex viewer,
and a first-pass signature-based recovery scanner (JPEG, PNG, PDF, ZIP, GZIP, 7Z, RIFF).
