# ByteRescue

**Storage Analysis & Data Recovery**

[![CI](https://github.com/CodingJeffRoblox/ByteRescue/actions/workflows/python-ci.yml/badge.svg)](https://github.com/CodingJeffRoblox/ByteRescue/actions/workflows/python-ci.yml)
[![Build](https://github.com/CodingJeffRoblox/ByteRescue/actions/workflows/build-windows.yml/badge.svg)](https://github.com/CodingJeffRoblox/ByteRescue/actions/workflows/build-windows.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey.svg)](https://www.microsoft.com/windows)
[![GitHub Stars](https://img.shields.io/github/stars/CodingJeffRoblox/ByteRescue?style=social)](https://github.com/CodingJeffRoblox/ByteRescue/stargazers)

> A read-oriented desktop utility for storage analysis, file inspection, hashing, hex viewing, and signature/text-based recovery.

**Current release:** `0.7.0` · **Status:** Early development

---

**Storage Analysis & Data Recovery**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.7+](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows-lightgrey.svg)](https://www.microsoft.com/windows)
[![GitHub Stars](https://img.shields.io/github/stars/CodingJeffRoblox/ByteRescue?style=social)](https://github.com/CodingJeffRoblox/ByteRescue/stargazers)
[![GitHub Forks](https://img.shields.io/github/forks/CodingJeffRoblox/ByteRescue?style=social)](https://github.com/CodingJeffRoblox/ByteRescue/network/members)

*Released: September 22, 2026*

**Repository:** [github.com/CodingJeffRoblox/ByteRescue](https://github.com/CodingJeffRoblox/ByteRescue)

## Project

ByteRescue is being developed as an open-source storage analysis and recovery project. The project currently focuses on Windows and is intentionally conservative about recovery claims: this prototype does **not** guarantee recovery of every file type, filesystem, or deleted file.

### Quick Links

- [Installation & Usage](#first-run)
- [Features](#features-in-this-prototype)
- [Support](SUPPORT.md)
- [Security Policy](SECURITY.md)
- [Contributing](CONTRIBUTING.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Report a Bug](https://github.com/CodingJeffRoblox/ByteRescue/issues/new?template=bug_report.yml)
- [Request a Feature](https://github.com/CodingJeffRoblox/ByteRescue/issues/new?template=feature_request.yml)
- [Releases](https://github.com/CodingJeffRoblox/ByteRescue/releases)

## Start the GUI

Easiest: double-click **`ByteRescue.bat`**. It's a thin shim that hands off to `ByteRescue.ps1`, which:

1. Requests Administrator privileges via a UAC prompt (physical-drive scanning needs them) -- a new,
   elevated console window opens; you can close the first one once it says so.
2. Checks for a working Python 3.11+, and if none is found, installs it automatically via `winget`
   (Windows' built-in package manager) and retries -- no manual download needed on most modern Windows
   10/11 systems. If `winget` isn't available, it prints a direct link to the python.org installer instead.
3. Launches the app.

Or, if you already have Python 3.11+ set up and just want to run it directly:

```powershell
python app.py
```

The GUI should open in a desktop window titled **ByteRescue — Storage Analysis & Data Recovery**.

## First run

Install the small dependencies:

```powershell
python -m pip install -r requirements.txt
```

Then:

```powershell
python app.py
```

## What's New in 0.7.0

- **Live console log output**: previously the log file (`logs/byterescue.log`) was the only place to see
  what ByteRescue was doing. Now, whenever it's run from a console (the normal case -- the elevated
  window `ByteRescue.ps1` opens stays open), the same events stream live to that window too. Set the
  `BYTERESCUE_DEBUG` environment variable to see verbose `DEBUG`-level output; every run also now logs
  its environment once at startup (version, Python build, OS, elevation status).
- **Fixed another GUI freeze, found while adding the above**: selecting "Physical Drive" as the Recovery
  Center's source used to block the whole window for several seconds (measured ~5.9s) shelling out to
  PowerShell/WMI directly on the GUI thread, with a redundant third call on every dropdown change on top
  of that. Backgrounded and cached, same pattern used for the main window's drive list in 0.5.0. See
  CHANGELOG.md for the mechanism and the new regression test.
- Repo cleanup: removed stray compiled `.pyc` files that had been committed before `.gitignore` excluded
  them.

## What's New in 0.6.1

A bug-hunt patch release, every button in the app driven through the real GUI to verify it. The
significant find: **"START RECOVERY SCAN" went permanently dead after the first scan** in any given
Recovery Center window -- clicking it again silently did nothing. See CHANGELOG.md for the mechanism
and the regression test that now guards it.

## What's New in 0.6.0

- **Real logging** (`logs/byterescue.log`): every run now writes a log file, and an "Open Log" button in
  the Recovery Center opens it directly. Previously, an error inside a GUI callback only ever printed to
  stderr, which is invisible when launched by double-clicking `ByteRescue.bat`.
- **Fixed a real bug this caught**: the Recovery Results table could permanently stop updating partway
  through a scan while the summary line kept reporting the true (larger) count -- see CHANGELOG.md for
  the full mechanism. Now covered by a dedicated regression test.

## What's New in 0.5.0

- **Animated startup splash screen**: shown while the main window is built and storage devices are
  detected. Reflects real startup work rather than a fixed fake delay.
- **Fixed a real freeze**: detecting storage devices (at startup and via "Refresh Drives") used to block
  the entire GUI while it shelled out to PowerShell/WMI. It's backgrounded now, same pattern the
  Recovery Center already used for scanning.

## What's New in 0.4.0

- **Launcher rewrite**: `ByteRescue.bat` now hands off to `ByteRescue.ps1`, which requests Administrator
  elevation via a UAC prompt, detects Python 3.11+, installs it automatically via `winget` if it's
  missing (with a PATH refresh so it works without reopening the window), and only then launches the
  app -- see [Start the GUI](#start-the-gui). Found and fixed three real bugs in the old all-batch
  launcher along the way, including one that made it fail on *every* run (see CHANGELOG.md).

## What's New in 0.3.0

- **Recover by File System now actually works for FAT12/16/32** (`byterescue/recovery/filesystem.py`):
  reads the volume's real directory table, including deleted entries, to recover files signature/text
  scanning can miss entirely -- and recovers each entry's original filename when it finds one. NTFS and
  exFAT are still not implemented and say so with a clear error rather than silently finding nothing.
  Deleted multi-cluster files are recovered by *assuming* contiguous allocation (FAT deletion normally
  erases the real cluster chain, not just the directory entry) -- labeled per-result, never hidden.
- **Fixed a real bug in physical-drive scanning**, found from actual hardware use: `pathlib.Path()`
  silently mangled `\\.\PhysicalDrive2` into `\\.\PhysicalDrive2\` (an extra trailing backslash from
  being parsed as a UNC path), which Windows then refused to open -- so raw-drive scans failed with
  "Access denied" even when ByteRescue was genuinely running elevated. Device paths are now kept as
  plain strings everywhere; a related bug (`os.stat()` "succeeding" on a device path but always
  reporting size 0, which would have made a drive scan silently "complete" having read nothing) is
  fixed alongside it.
- **Recovery Center Help/Docs tab**: every mode, control, and results-table column explained in plain
  language, without leaving the window.

## What's New in 0.2.0

A Recovery Center rebuild: the old single-button "Recover by Signature" scanner is now a real recovery
engine with several genuinely different recovery strategies, not just a bigger dictionary of magic bytes.

- **Recovery Center window** with four modes (see [Recovery Modes](#recovery-modes) below): Recover by
  Signature, Recover Text Files, Deep / Raw Scan, and Recover by File System (a placeholder as of this
  version -- FAT12/16/32 support landed in 0.3.0, see above).
- **Text recovery** with no fake magic signature: readable ASCII/UTF-8/UTF-16 LE/UTF-16 BE runs are found
  by pattern and scored for confidence, since plain text has no universal header.
- **A real ZIP implementation**: Local File Header, Central Directory Header, and End Of Central Directory
  are handled as the three distinct structures they are. A multi-entry ZIP is carved as one valid archive
  (verified against its real End Of Central Directory), not one broken fragment per internal entry.
- **Structural validation, not just a signature match**: recovered JPEG/PNG/GIF/BMP/TIFF/WEBP are checked
  with Pillow, ZIP with `zipfile`, SQLite with `PRAGMA integrity_check`, WAV with the `wave` module, GZIP by
  decompressing it. Every result is labeled Passed / Partial / Failed / Unknown -- a signature match alone
  is never reported as a successful recovery.
- **Chunked scanning with overlap** (`byterescue/recovery/scanner.py`) for large sources, so a signature
  split across a chunk boundary is still detected, without loading the whole source into RAM.
- **Pause / Resume / Stop**, live progress (offset, scanned/total, speed, ETA, candidates found/valid/
  rejected), duplicate detection, a JSON recovery report you can export, and Hex Viewer integration
  (selecting a result jumps the Hex Viewer to and highlights its offset).
- **New validated formats**: BMP, GIF, TIFF, RAR, legacy Office (OLE), MKV/WebM, MP3 (ID3 tag only), and
  real structural carving for Windows PE (.exe/.dll) and ELF executables, and MP4/MOV (via ISO-BMFF box
  walking). See [Recovery Signatures](#recovery-signatures-what-is-actually-implemented) for exactly what
  "supported" means for each one.
- Recovery/carving logic moved out of the GUI into `byterescue/recovery/` (`signatures.py`, `text_recovery.py`,
  `scanner.py`), with a real test suite in `tests/` covering carving correctness, chunk-boundary handling,
  cancellation, duplicate detection, and destination-safety checks.
- Fixed several bugs found while building this: the Hex Viewer's Search box referenced an undefined
  variable and always crashed when used; the multi-entry ZIP carving described above; a scanner that loaded
  entire source files into RAM despite a comment claiming otherwise; and the main Analysis panel being
  silently editable instead of read-only.

## What's New in 0.1.2

This development release focuses on making the desktop interface easier to use, safer to inspect, and more resilient during recovery operations.

- Added "What am I looking at?" tab
  - Explains physical drives
  - Capacity
  - Interfaces
  - Status
  - Analysis results
  - SHA-256
  - Hex viewer
  - File carving/recovery
  - SSD/TRIM limitations
  - Safe recovery practices
- Fixed the white hover issue
  - Buttons now have dark hover colors
  - Tabs have dark hover colors
  - Drive selection has a dark highlight
  - No more white flashing when hovering
- Improved crash handling
  - Startup errors are displayed instead of silently returning to the command prompt
  - File errors produce a readable error dialog
  - Recovery errors are caught
  - GUI remains responsive during recovery scans
  - Recovery buttons are temporarily disabled while scanning
- Improved the Hex Viewer
  - Scrollbars
  - Dark interface
  - Larger viewing area
  - 128 KB preview
- Improved recovery
  - Prevents overwriting existing recovered files
  - Shows scan status
  - Recovery results are displayed in the GUI

## Project Tags

`data-recovery` `file-recovery` `storage-analysis` `forensics` `windows` `python` `gui` `hex-viewer` `disk-analysis` `file-carving` `ntfs` `fat32` `open-source` `mit-license`

## What is ByteRescue?

ByteRescue is a storage analysis and data recovery tool designed for Windows systems. It helps you:
- Analyze physical drives and storage devices (metadata only -- see [Supported File Systems](#supported-file-systems))
- Inspect files and folders at the byte level
- Attempt to recover deleted-but-not-yet-overwritten data using signature carving or text-pattern search
- Understand drive health and storage characteristics
- Perform read-only analysis -- ByteRescue does not currently do forensic-grade acquisition (hashed imaging,
  chain-of-custody, write-blocking enforcement); it is a read-oriented analysis tool, not a certified
  forensic suite

## Recovery Modes

The Recovery Center has four modes, all of which do real recovery now:

| Mode | What it actually does |
|---|---|
| **Recover by Signature** | Searches a chosen file or disk image for the byte signatures listed in [Recovery Signatures](#recovery-signatures-what-is-actually-implemented) below. |
| **Recover Text Files** | Searches for long, plausible runs of readable ASCII/UTF-8/UTF-16 text and scores each one's confidence. Plain text has no magic header, so this is pattern detection, not signature matching. |
| **Deep / Raw Scan** | The same signature search as "Recover by Signature", but reads the source in fixed-size chunks with an overlap buffer instead of memory-mapping it, so a signature split across a chunk boundary is still found and very large sources don't need to fit in memory. Intended for raw physical-drive sources. |
| **Recover by File System** | Reads the volume's actual FAT12/16/32 directory table (`byterescue/recovery/filesystem.py`) -- including deleted entries -- to recover files the other modes can miss, with the original filename when one is found. **NTFS and exFAT are not implemented** and report a clear error rather than silently finding nothing. A deleted file spanning more than one cluster is recovered by *assuming* contiguous allocation (FAT deletion normally erases the real cluster chain, not just the directory entry) -- every such result says so and is marked lower confidence; a file that fits in a single cluster needs no such assumption and is marked High confidence. |

A "verified" recovered item had its end offset proven from the format's own structure (an exact length
field, a checksummed footer, or a fully walked container/section table). An "unverified" item had no
reliable end marker, so a safety cap was used instead -- treat it as a guess, not a confirmed result.
Every item also gets a separate structural **validation** result (Passed / Partial / Failed / Unknown) from
actually trying to parse it, because a matching signature is not proof of a complete, undamaged file.

## When to Use ByteRescue

### Common Use Cases
- **Accidental Deletion**: Recover files that were accidentally deleted from a drive
- **Corrupted Storage**: Analyze drives that are having read issues or corruption
- **Drive Analysis**: Understand the health, capacity, and interface of storage devices
- **File Inspection**: Examine file contents using hex view and verify file integrity with SHA-256
- **Data Forensics**: Perform read-only analysis for investigative purposes
- **USB Recovery**: Recover files from USB drives that may have been improperly ejected
- **Backup Verification**: Hash files to verify backup integrity

### Situations Where ByteRescue Helps
- After a virus or malware attack that deleted files
- When a drive becomes inaccessible due to corruption
- To recover photos from a formatted SD card
- To analyze why a drive is performing poorly
- To verify that files haven't been tampered with
- To recover documents from a failing hard drive
- To inspect unknown files for security analysis

## Supported File Systems

**FAT12/16/32 only, for filesystem-aware recovery** (`byterescue/recovery/filesystem.py`, used by the
"Recover by File System" mode) -- it parses the real boot sector/BPB, walks directories recursively
(short 8.3 and VFAT long-filename entries), and recovers deleted entries whose data hasn't been
overwritten yet. **NTFS and exFAT are not implemented**: selecting that mode against one reports a clear
"not a recognizable FAT12/16/32 volume" error rather than silently finding nothing. Outside of that one
mode, ByteRescue still only ever does two filesystem-agnostic things: (1) reads ordinary files/folders
through normal Windows file APIs -- which works on whatever filesystem Windows itself mounted, because
that's Windows doing its job, not ByteRescue implementing filesystem support -- and (2) carves raw bytes
out of a file or device path (signature/text modes), which never looks at directory entries, an MFT, or
a FAT allocation table at all.

Even within FAT12/16/32, filesystem-mode recovery has a real limitation worth understanding: deleting a
file on FAT erases that file's cluster CHAIN in the FAT table (not just the directory entry), so a
deleted file's later clusters are usually already gone even when its name/size/start-cluster survive.
ByteRescue therefore *assumes contiguous allocation* for a deleted file spanning more than one cluster --
the same approach classic FAT-undelete tools use, and the same reason they've always struggled with
fragmented deleted files. Every such result is labeled with this assumption and marked lower confidence;
a deleted file that fits in a single cluster needs no such assumption and is marked High confidence.

### Physical drive listing vs. physical drive scanning
The Storage Devices list uses WMI/CIM (`Get-CimInstance Win32_DiskDrive`) for metadata only -- model,
capacity, interface, status. No raw sector access happens there. Physical-drive *scanning* (Deep / Raw
Scan mode, or choosing "Physical Drive" as a source) opens the raw device path (`\\.\PhysicalDriveN`)
directly, which needs Administrator privileges and has not been verified against real hardware in this
build -- it is real code, not a stub, but treat it as unverified until you've tried it on a real device;
if it fails to open the device it will report a read error rather than do anything unsafe.

### Important Limitations
- **SSD TRIM**: Modern SSDs use TRIM, which can make deleted data unrecoverable. The Recovery Center shows
  a warning when the selected physical drive reports as SSD/NVMe (via `Get-PhysicalDisk`'s MediaType, which
  is more reliable for this than `Win32_DiskDrive`). ByteRescue cannot bypass TRIM -- nothing can, once the
  underlying flash has actually been erased.
- **Encrypted Drives**: BitLocker or other encryption must be unlocked first; ByteRescue does not decrypt anything.
- **RAID Arrays**: Not supported -- no RAID metadata parsing or member reconstruction exists.
- **Write-Protected Media**: Read-only physical write protection is a property of the device itself, not something ByteRescue manages.

## Recovery Signatures (what is actually implemented)

Every entry below has real carving logic behind it in `byterescue/recovery/signatures.py` -- this list is
intentionally short rather than padded, and each row says plainly whether the recovered file's end offset
is actually proven or just an estimate.

| Format | End offset | Notes |
|---|---|---|
| JPEG | Heuristic (last End-of-Image before a size cap) | Handles embedded EXIF thumbnails correctly; still a heuristic, not a proof |
| PNG | Verified (checksummed IEND footer) | |
| PDF | Heuristic (last %%EOF before a size cap) | Captures multi-revision (incrementally saved) PDFs |
| ZIP | Verified (real End Of Central Directory) | A multi-entry ZIP is carved as one archive, not one fragment per entry. Recognized as `.docx`/`.xlsx`/`.pptx` when the archive contents say so -- OOXML files are ordinary ZIPs |
| GZIP, 7-Zip, FLAC | Unverified (no footer exists for these formats; capped) | |
| WAV / AVI / WebP (RIFF) | Verified (exact length stored in the RIFF header) | |
| SQLite | Verified (exact length from page size x page count) | |
| BMP | Verified when accepted | The 2-byte "BM" magic alone is too weak to trust; a candidate is rejected outright unless its embedded size field and DIB header size both look real |
| Windows PE (.exe/.dll) | Verified when accepted | "MZ" alone is too weak to trust; rejected outright unless it leads to a real PE header, whose section table (and signature block, if present) gives the real end |
| ELF | Verified when accepted | End computed from the section header table; a stripped binary with no section headers is rejected, not guessed at |
| MP4 / MOV | Verified when accepted | End computed by walking the ISO-BMFF box structure from the `ftyp` box |
| GIF, TIFF, RAR, legacy Office (OLE), MKV/WebM | Unverified (no simple footer or requires a full container parser not yet written; capped) | |
| MP3 | Not really -- detects an ID3v2 tag only | Raw MPEG frame-sync bytes are deliberately not used as a signature; they occur constantly inside valid audio and would produce far too many false positives |

Camera RAW formats (.cr2/.nef/etc.), legacy/plain document formats with no binary signature (.txt/.csv/.rtf
-- use Recover Text Files for these), and video/audio container internals beyond what's listed above are
not implemented.

## Best Practices

### Before Recovery
- Stop using the affected drive immediately to prevent overwriting
- If possible, create a disk image before recovery attempts
- Run ByteRescue as Administrator for physical disk access
- Ensure you have a separate destination drive for recovered files

### During Recovery
- Never save recovered files back to the source drive
- Use the Hex Viewer to verify file integrity before recovery
- Check the SHA-256 hash to confirm file authenticity
- Monitor the scan status for progress updates

### After Recovery
- Verify recovered files open correctly
- Back up important recovered data immediately
- Consider the original drive may be failing and plan for replacement

## Features in this prototype

- Windows physical disk detection (metadata only)
- HDD / SSD / USB device listing, with best-effort SSD/NVMe TRIM warnings
- Folder analysis
- File analysis with SHA-256 hashing
- Hex viewer with search, a hex/byte reference lookup, click-a-line explanations, and jump-to-offset
  from a recovery result -- strictly read-only, it never writes back to the source
- Recovery Center: signature-based recovery, text-pattern recovery, chunked "Deep / Raw Scan" reading, and
  FAT12/16/32 filesystem-aware recovery, plus an in-window Help/Docs tab
  (see [Recovery Modes](#recovery-modes) and [Recovery Signatures](#recovery-signatures-what-is-actually-implemented))
- Structural validation of recovered files (Pillow / zipfile / sqlite3 / wave / gzip), duplicate detection,
  pause/resume/stop scan controls, live progress, and an exportable JSON recovery report
- Recovery destination selection with a same-drive-as-source warning
- Read-oriented analysis interface, dark desktop GUI

Physical-drive scanning requires Administrator privileges on Windows. Recovered files are never written
back to the source -- you always choose a separate destination folder.

**Important:** SSD TRIM can make deleted data unrecoverable, and ByteRescue cannot bypass it. Signature and
text-pattern carving are read-only, best-effort recovery methods -- a match is not a guarantee.

## Testing

```powershell
cd tests
python -m unittest test_signatures test_text_recovery test_scanner test_filesystem test_gui_recovery_center -v
```

The suite (`tests/`, 55 tests) runs against synthetic fixtures built in memory (`tests/fixtures.py`) --
JPEG with an embedded EXIF thumbnail, a multi-revision PDF, a multi-entry ZIP, a minimal but structurally
real PE and ELF binary, an MP4 box tree, hand-built byte-exact FAT16 and FAT32 volume images, ASCII/
UTF-8/UTF-16 text samples, and more -- never real files. It covers carving correctness (including the
JPEG-thumbnail and multi-entry-ZIP cases above), text-encoding detection, false-positive rejection,
chunk-boundary-split signatures, duplicate detection, cancellation, destination-safety checks, device-path
handling (a regression test for the `pathlib` bug described in [What's New in 0.3.0](#whats-new-in-030)),
FAT12/16/32 directory parsing (deleted files, multi-cluster chains, subdirectories, long filenames),
SHA-256, and (`test_gui_recovery_center.py`, real Tkinter widgets, needs a display) that the Recovery
Results table survives a malformed result item without silently losing every row after it -- see
[What's New in 0.6.0](#whats-new-in-060).

## License

ByteRescue is open source software released under the MIT License. See the [LICENSE](LICENSE) file for the full license text.

### Project Structure

```text
ByteRescue/
├── app.py                      # launcher: `python app.py`
├── byterescue/
│   ├── app.py                  # GUI only (Tkinter) -- ByteRescue main window + RecoveryCenter
│   ├── applog.py                # log file setup + Tk/thread exception hooks (logs/byterescue.log)
│   └── recovery/                # the actual recovery engine, importable/testable without Tkinter
│       ├── signatures.py       # SIGNATURES metadata + carve/validate logic
│       ├── text_recovery.py    # text-pattern detection (ASCII/UTF-8/UTF-16)
│       ├── filesystem.py       # FAT12/16/32 boot sector, directory, and deleted-entry parsing
│       ├── scanner.py          # ChunkedReader, RecoveryScan (pause/resume/cancel/progress/log)
│       └── hex_reference.py    # educational HEX_CODE_REFERENCE (never used by the scanner)
├── logs/                        # created at runtime, git-ignored -- byterescue.log
├── tests/
│   ├── fixtures.py             # synthetic test files (and FAT16/FAT32 images), built in memory
│   ├── test_signatures.py
│   ├── test_text_recovery.py
│   ├── test_scanner.py
│   ├── test_filesystem.py
│   └── test_gui_recovery_center.py
├── requirements.txt
├── ByteRescue.bat               # thin double-click shim -> ByteRescue.ps1
├── ByteRescue.ps1               # real launcher: elevate, ensure Python, launch
├── .github/
│   ├── ISSUE_TEMPLATE/
│   └── workflows/
├── CHANGELOG.md
├── CONTRIBUTING.md
├── SUPPORT.md
├── SECURITY.md
├── CODE_OF_CONDUCT.md
└── LICENSE
```

### Contributing

As an open source project, contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines on how to contribute, including:
- Setting up your development environment
- Code style guidelines
- Submitting pull requests
- Development priorities and focus areas

**Contribute on GitHub:** [https://github.com/CodingJeffRoblox/ByteRescue/fork](https://github.com/CodingJeffRoblox/ByteRescue/fork)

### Support

For help with using ByteRescue, troubleshooting, and common issues, please see [SUPPORT.md](SUPPORT.md). It includes:
- Installation and setup help
- Common issues and solutions
- Data recovery best practices
- When recovery isn't possible
- Community support resources

**Report Issues:** [https://github.com/CodingJeffRoblox/ByteRescue/issues](https://github.com/CodingJeffRoblox/ByteRescue/issues)
**Discussions:** [https://github.com/CodingJeffRoblox/ByteRescue/discussions](https://github.com/CodingJeffRoblox/ByteRescue/discussions)

### Disclaimer

This software is provided for educational and data recovery purposes. The authors are not responsible for any data loss or damage that may occur while using this software. Always backup important data and use recovery tools responsibly. 
