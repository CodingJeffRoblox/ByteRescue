# ByteRescue 0.1.1

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
