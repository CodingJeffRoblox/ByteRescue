# ByteRescue

**Storage Analysis & Data Recovery**

[![CI](https://github.com/CodingJeffRoblox/ByteRescue/actions/workflows/python-ci.yml/badge.svg)](https://github.com/CodingJeffRoblox/ByteRescue/actions/workflows/python-ci.yml)
[![Build](https://github.com/CodingJeffRoblox/ByteRescue/actions/workflows/build-windows.yml/badge.svg)](https://github.com/CodingJeffRoblox/ByteRescue/actions/workflows/build-windows.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey.svg)](https://www.microsoft.com/windows)
[![GitHub Stars](https://img.shields.io/github/stars/CodingJeffRoblox/ByteRescue?style=social)](https://github.com/CodingJeffRoblox/ByteRescue/stargazers)

> A read-oriented desktop utility for storage analysis, file inspection, hashing, hex viewing, and basic signature-based recovery.

**Current release:** `0.1.2` · **Status:** Early development

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

From the `ByteRescue` folder:

```powershell
python app.py
```

Or double-click:

```text
ByteRescue.bat
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
- Analyze physical drives and storage devices
- Inspect files and folders at the byte level
- Recover deleted files using signature-based carving
- Understand drive health and storage characteristics
- Perform forensic-grade analysis with read-only operations

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

> **Current limitation:** the prototype does not yet implement full filesystem parsing. The list below describes storage/filesystem environments the project is intended to support as the low-level recovery engine develops; it should not be read as a claim that every filesystem feature is currently implemented.

ByteRescue works with Windows-compatible file systems through physical disk access:

### Primary Support
- **NTFS**: The primary Windows file system (Windows XP and later)
- **FAT32**: Compatible with older systems and portable drives
- **exFAT**: Optimized for flash drives and large files

### Physical Drive Support
- **HDD (Hard Disk Drives)**: Traditional spinning platter drives
- **SSD (Solid State Drives)**: Flash-based storage (note TRIM limitations)
- **USB Drives**: External storage devices
- **SD Cards**: Memory cards via card readers
- **External Hard Drives**: USB-connected external storage

### Important Limitations
- **SSD TRIM**: Modern SSDs use TRIM which can make deleted data unrecoverable
- **Write-Protected Media**: Some SD cards/USB drives have physical write protection
- **Encrypted Drives**: BitLocker or other encryption must be unlocked first
- **RAID Arrays**: Individual RAID member analysis only (not RAID reconstruction)

## Recovery Use Cases by File Type

> File extensions alone do not determine whether a deleted file can be recovered. Current carving support is limited to the signatures implemented by the prototype.

### Documents
- **Office Files**: .doc, .docx, .xls, .xlsx, .ppt, .pptx
- **PDFs**: .pdf documents
- **Text Files**: .txt, .rtf, .csv
- **Use Case**: Recover important work documents, tax returns, contracts

### Images
- **Photos**: .jpg, .jpeg, .png, .gif, .bmp, .tiff
- **Raw Files**: .raw, .cr2, .nef (camera raw formats)
- **Use Case**: Recover family photos, vacation pictures, professional photography

### Videos
- **Video Files**: .mp4, .avi, .mov, .mkv, .wmv
- **Use Case**: Recover home videos, drone footage, screen recordings

### Audio
- **Audio Files**: .mp3, .wav, .flac, .aac
- **Use Case**: Recover music collections, voice recordings, podcasts

### Archives
- **Compressed Files**: .zip, .rar, .7z
- **Use Case**: Recover backup archives, compressed project files

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

- Windows physical disk detection
- HDD / SSD / USB device listing
- Folder analysis
- File analysis
- SHA-256 hashing
- Hex viewer
- Basic file-signature recovery
- Recovery destination selection
- Read-oriented analysis interface
- Dark desktop GUI

For physical-disk access and future low-level acquisition features, Administrator privileges may be required on Windows. Do not save recovered files back onto the source drive.

**Important:** SSD TRIM can make deleted data unrecoverable. Signature carving is a basic first-pass recovery feature in this release.

## License

ByteRescue is open source software released under the MIT License. See the [LICENSE](LICENSE) file for the full license text.

### Project Structure

```text
ByteRescue/
├── app.py
├── byterescue/
├── requirements.txt
├── ByteRescue.bat
├── .github/
│   ├── ISSUE_TEMPLATE/
│   └── workflows/
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
