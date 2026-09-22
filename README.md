# ByteRescue 0.1.2

**Storage Analysis & Data Recovery**

*Released: September 22, 2026*

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

For physical-disk access and future low-level acquisition features, run as Administrator. Do not save recovered files back onto the source drive.

**Important:** SSD TRIM can make deleted data unrecoverable. Signature carving is a basic first-pass recovery feature in this release.

## License

ByteRescue is open source software released under the MIT License. See the [LICENSE](LICENSE) file for the full license text.

### Contributing

As an open source project, contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines on how to contribute, including:
- Setting up your development environment
- Code style guidelines
- Submitting pull requests
- Development priorities and focus areas

### Support

For help with using ByteRescue, troubleshooting, and common issues, please see [SUPPORT.md](SUPPORT.md). It includes:
- Installation and setup help
- Common issues and solutions
- Data recovery best practices
- When recovery isn't possible
- Community support resources

### Disclaimer

This software is provided for educational and data recovery purposes. The authors are not responsible for any data loss or damage that may occur while using this software. Always backup important data and use recovery tools responsibly.
"# ByteRescue" 
