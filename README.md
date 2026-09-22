# ByteRescue 0.1.2

**Storage Analysis & Data Recovery**

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
"# ByteRescue" 
