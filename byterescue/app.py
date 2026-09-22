
import hashlib
import json
import mmap
import os
import platform
import struct
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

APP = "ByteRescue"

# Formats the recovery scanner actually knows how to carve.
# Every entry needs real logic in _scan_signatures/_carve_* -- don't add one "for show".
# Avoid 1-2 byte magics (e.g. "BM", "MZ"); they false-positive constantly without a validator.
# Each value: (header bytes, output extension, carver name)
SIGS = {
    "JPEG":   (b"\xff\xd8\xff", ".jpg", "jpeg"),
    "PNG":    (b"\x89PNG\r\n\x1a\n", ".png", "png"),
    "PDF":    (b"%PDF-", ".pdf", "pdf"),
    "ZIP":    (b"PK\x03\x04", ".zip", "zip"),
    "GZIP":   (b"\x1f\x8b\x08", ".gz", "capped"),
    "7Z":     (b"7z\xbc\xaf'\x1c", ".7z", "capped"),
    "FLAC":   (b"fLaC", ".flac", "capped"),
    "RIFF":   (b"RIFF", ".riff", "riff"),
    "SQLITE": (b"SQLite format 3\x00", ".sqlite", "sqlite"),
}

# Caps for "no reliable footer" carves -- not a real end-of-file, just a ceiling
# so one stray header can't dump gigabytes of trailing junk into one file.
JPEG_MAX_BYTES = 64 * 1024 * 1024          # JPEGs essentially never exceed this
PDF_MAX_BYTES = 256 * 1024 * 1024
UNVERIFIED_CAP_BYTES = 512 * 1024 * 1024   # GZIP / 7Z / FLAC / fallback cases

# Educational only -- powers the Hex Viewer's lookup/click-a-line features.
# Never read by the scanner, so it's safe to keep single bytes/ranges in here.
HEX_CODE_REFERENCE = {
    # --- Exact file signatures (magic numbers) -----------------------------
    "FF D8 FF": "JPEG - Start of Image (SOI) marker, followed by the next marker segment",
    "FF D9": "JPEG - End of Image (EOI) marker",
    "89 50 4E 47 0D 0A 1A 0A": "PNG file header (full 8-byte signature). The trailing 0D 0A 1A 0A bytes exist specifically to detect corruption from text-mode/line-ending transfers",
    "89 50 4E 47": "PNG signature (first 4 bytes only -- see the full 8-byte PNG entry for the reliable version)",
    "49 45 4E 44 AE 42 60 82": "PNG - IEND chunk (end of image), including its fixed CRC. Because IEND always has zero-length data, this exact 8-byte sequence is what reliably marks the end of a PNG file",
    "49 45 4E 44": "PNG - 'IEND' chunk type only (no CRC) -- the 4 bytes alone are a weaker match than the full 8-byte IEND+CRC entry",
    "25 50 44 46 2D": "PDF file header (%PDF-, includes version number afterward)",
    "25 25 45 4F 46": "PDF - %%EOF marker. A PDF can legally contain more than one of these (incremental updates); the LAST one in the file is the one that matters",
    "50 4B 03 04": "ZIP - Local File Header. Marks the start of ONE archived entry -- a ZIP can contain many of these, so finding one does not by itself mean the whole archive can be recovered from that point",
    "50 4B 01 02": "ZIP - Central Directory File Header. Part of the archive's file listing, not a new archive and not an archive boundary",
    "50 4B 05 06": "ZIP - End Of Central Directory (EOCD). Marks where the archive's central directory (file listing) ends -- this is what actually marks the end of a ZIP file. This is a plain ZIP signature, not Office-specific; Office Open XML files (.docx/.xlsx/.pptx) are ordinary ZIP archives internally and use this same structure",
    "50 4B 07 08": "ZIP - data descriptor (used when an entry's sizes/CRC are written after its compressed data instead of in the local header)",
    "1F 8B 08": "GZIP file header (the trailing 08 is the compression method -- deflate, the only one used in practice)",
    "37 7A BC AF 27 1C": "7-Zip file header (full 6-byte signature)",
    "37 7A BC AF": "7-Zip signature (first 4 bytes only -- see the full 6-byte entry)",
    "52 49 46 46": "RIFF container header -- a generic wrapper. The actual format (WAV, AVI, WEBP, and others) is given by a 4-byte tag at offset 8, and the 4 bytes right after 'RIFF' are the exact remaining file length",
    "53 51 4C 69 74 65 20 66 6F 72 6D 61 74 20 33 00": "SQLite database file header (full 16-byte signature, 'SQLite format 3\\0')",
    "D0 CF 11 E0 A1 B1 1A E1": "OLE Compound File Binary Format header (legacy Office 97-2003 .doc/.xls/.ppt, and a few other formats). Full 8-byte signature",
    "D0 CF 11 E0": "OLE compound document signature (first 4 bytes only -- see the full 8-byte entry)",
    "42 4D": "BMP file header ('BM'). Only 2 bytes, so on its own this is a weak/common pattern -- BMP also stores its exact file size as a 4-byte field right after these 2 bytes, which is needed to carve it reliably",
    "47 49 46 38 37 61": "GIF87a file header",
    "47 49 46 38 39 61": "GIF89a file header",
    "49 49 2A 00": "TIFF file header, little-endian ('II') byte order",
    "4D 4D 00 2A": "TIFF file header, big-endian ('MM') byte order",
    "52 61 72 21 1A 07 00": "RAR archive header (RAR 1.5-4.x)",
    "52 61 72 21 1A 07 01 00": "RAR5 archive header",
    "66 74 79 70": "MP4/MOV 'ftyp' box type tag -- normally found at byte offset 4 of the file (preceded by a 4-byte box-size field, which varies, so there is no single fixed byte sequence for 'the MP4 header')",
    "1A 45 DF A3": "EBML header -- container format used by MKV and WebM (and a few other formats). No simple end-of-file marker exists; a full EBML/Matroska parser is needed to find the real end",
    "66 4C 61 43": "FLAC audio file header ('fLaC')",
    "49 44 33": "ID3v2 tag header -- commonly found at the start of MP3 files, but its presence does not guarantee valid/complete MP3 audio follows, and plenty of real MP3 files have no ID3v2 tag at all",
    "7F 45 4C 46": "ELF file header (Linux/Unix executables, shared libraries, and object files)",
    "4D 5A": "MZ header ('MZ', Windows/DOS executable). Only 2 bytes -- far too common to use alone; reliable EXE detection needs this PLUS a validated 'PE\\0\\0' header located via the pointer stored in the DOS header",
    "50 45 00 00": "PE header signature ('PE\\0\\0'). Not found at a fixed file offset -- its real location is read from a pointer field in the preceding DOS/MZ header",

    # --- Byte order marks ---------------------------------------------------
    "FE FF": "UTF-16 Big Endian byte order mark (BOM)",
    "FF FE": "UTF-16 Little Endian byte order mark (BOM)",
    "EF BB BF": "UTF-8 byte order mark (BOM)",

    # --- Control characters (0x00-0x1F, plus space) -------------------------
    "00": "Null byte (string terminator, padding) -- extremely common, not a file signature on its own",
    "01": "Start of Heading (SOH)",
    "02": "Start of Text (STX)",
    "03": "End of Text (ETX)",
    "04": "End of Transmission (EOT)",
    "05": "Enquiry (ENQ)",
    "06": "Acknowledge (ACK)",
    "07": "Bell (audible alert)",
    "08": "Backspace",
    "09": "Horizontal Tab",
    "0A": "Line Feed / newline. Alone, this is the Unix/Linux line ending; paired right after a 0D (0D 0A) it forms the Windows/DOS line ending",
    "0B": "Vertical Tab",
    "0C": "Form Feed (page break)",
    "0D": "Carriage Return. Alone, this is the classic Mac OS (pre-OS X) line ending; paired with a following 0A (0D 0A) it forms the Windows/DOS line ending",
    "0E": "Shift Out",
    "0F": "Shift In",
    "1A": "Substitute (Ctrl+Z) -- used historically as a text-file EOF marker on CP/M and DOS",
    "1B": "Escape (ESC)",
    "20": "Space character -- one of the most common bytes in any text data, not a file signature",
    "FF": "Byte value 255 -- often used as padding, a fill value, or (as the first byte of a 2-byte marker) inside JPEG data. Far too common on its own to be a file signature",

    # --- Line endings (multi-byte) ------------------------------------------
    "0D 0A": "Windows/DOS line ending (CRLF)",
    "0D 0A 0D 0A": "Blank line / section separator formed by two CRLF line endings in a row (e.g. marks the end of HTTP headers)",
    "0A 0A": "Blank line / paragraph separator formed by two Unix (LF) line endings in a row",

    # --- Common byte-pattern filler -----------------------------------------
    "00 00 00 00": "Four null bytes -- common alignment/padding, not a signature",
    "FF FF FF FF": "Four 0xFF bytes -- common padding, erased-flash value, or a sentinel/max-value marker, not a signature",

    # --- Loosely-structured text conventions (not true binary magic numbers) -
    "3C 21 44 4F 43 54 59 50 45": "Common start of an HTML5 document (<!DOCTYPE). This is a text convention, not a binary magic number -- it is case-sensitive here, not all valid HTML includes a DOCTYPE, and other SGML/XML-ish documents can start the same way",
    "3C 68 74 6D 6C": "Literal text '<html' -- a common but not guaranteed HTML start tag. Real HTML tags are case-insensitive, so this exact byte sequence will miss '<HTML' or '<Html'",

    # --- Reference-only byte ranges (NEVER used by the scanner) -------------
    "20-7E": "Byte range: printable ASCII characters (space to tilde). Reference only -- describes a class of bytes, not a signature",
    "41-5A": "Byte range: uppercase letters A-Z. Reference only",
    "61-7A": "Byte range: lowercase letters a-z. Reference only",
    "30-39": "Byte range: digits 0-9. Reference only",
}


def powershell(script):
    try:
        p = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),  # no flashing console
        )
        return p.stdout.strip()
    except Exception:
        return ""


def get_disks():
    # Metadata only (WMI/CIM) -- no raw \\.\PhysicalDriveN handle is ever opened.
    if platform.system() != "Windows":
        return []
    script = r"""
Get-CimInstance Win32_DiskDrive |
Select-Object Index,Model,InterfaceType,MediaType,Size,SerialNumber,Status |
ConvertTo-Json -Compress
"""
    out = powershell(script)
    if not out:
        return []
    try:
        data = json.loads(out)
        return data if isinstance(data, list) else [data]
    except Exception:
        return []


def human(value):
    try:
        n = float(value)
    except Exception:
        return "—"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    i = 0
    while n >= 1024 and i < len(units) - 1:
        n /= 1024
        i += 1
    return f"{n:.2f} {units[i]}"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# `data` below is a read-only mmap of the source file, so carving works
# straight off disk without holding the whole file in RAM.
# Carvers return (end_offset, verified), or (end_offset, ext, verified) for
# RIFF since its extension depends on content, or None if no match at all.

def _carve_footer_last(data, start_i, header_len, footer, next_header, cap):
    # Last footer before the next header (not the first) -- avoids truncating
    # at a JPEG's embedded EXIF thumbnail EOI or an earlier PDF %%EOF revision.
    # Still just a heuristic, so callers should treat the result as unverified.
    bound = len(data)
    if next_header is not None:
        bound = min(bound, next_header)
    bound = min(bound, start_i + cap)

    last = -1
    pos = start_i + header_len
    while True:
        j = data.find(footer, pos, bound)
        if j < 0:
            break
        last = j
        pos = j + 1
    if last < 0:
        return None
    return (last + len(footer), False)


def _carve_zip(data, i):
    # A ZIP can have many Local File Headers (one per entry) -- only the End
    # Of Central Directory record marks where the archive actually ends.
    # EOCD length varies (0-65535 byte comment field), so read it, don't guess.
    eocd = b"PK\x05\x06"
    best = None
    pos = i
    while True:
        e = data.find(eocd, pos)
        if e < 0:
            break
        if e + 22 <= len(data):
            (comment_len,) = struct.unpack_from("<H", data, e + 20)
            end = e + 22 + comment_len
            if end <= len(data):
                best = end
        pos = e + 1
    if best is None:
        return None
    return (best, True)


def _carve_riff(data, i):
    # RIFF stores its own length (4 bytes right after "RIFF"), so the real end
    # is computable, not guessed. Offset-8 tag also gives the real extension.
    if i + 12 > len(data):
        return None
    (size,) = struct.unpack_from("<I", data, i + 4)
    fourcc = data[i + 8:i + 12]
    ext = {b"WAVE": ".wav", b"AVI ": ".avi", b"WEBP": ".webp"}.get(fourcc, ".riff")
    end = i + 8 + size
    if size >= 4 and end <= len(data):
        return (end, ext, True)
    # The size field is implausible (truncated/damaged capture) -- fall back
    # to whatever remains in the file, clearly marked unverified.
    fallback_end = min(len(data), i + 8 + min(max(size, 0), UNVERIFIED_CAP_BYTES))
    return (fallback_end, ext, False)


def _carve_sqlite(data, i):
    # Header stores page size (offset 16, value 1 means 65536) and page count
    # (offset 28) -- page_size * page_count is the documented exact file size.
    if i + 32 > len(data):
        return None
    (page_size,) = struct.unpack_from(">H", data, i + 16)
    if page_size == 1:
        page_size = 65536
    (page_count,) = struct.unpack_from(">I", data, i + 28)
    if page_size < 512 or page_size > 65536 or (page_size & (page_size - 1)) != 0:
        return None  # not a plausible page size -- almost certainly a false-positive match
    if page_count == 0:
        return None
    end = i + page_size * page_count
    if end > len(data):
        return None
    return (end, True)


class ByteRescue(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ByteRescue — Storage Analysis & Data Recovery")
        self.geometry("1220x760")
        self.minsize(1000, 650)
        self.configure(bg="#0f1318")
        self.path = None
        self._busy = False
        self.protocol("WM_DELETE_WINDOW", self.safe_close)

        self.configure_styles()
        self.build_ui()
        self.after(100, self.refresh_disks)

    def configure_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        # Explicit hover colors so ttk buttons do not flash white.
        style.configure(
            "TButton",
            background="#252c36",
            foreground="#e7ebf2",
            bordercolor="#3a4350",
            lightcolor="#252c36",
            darkcolor="#252c36",
            padding=(12, 8),
        )
        style.map(
            "TButton",
            background=[
                ("active", "#343d49"),
                ("pressed", "#1d232c"),
                ("disabled", "#171b21"),
            ],
            foreground=[("disabled", "#687180"), ("active", "#ffffff")],
            bordercolor=[("active", "#4c5868")],
        )

        style.configure(
            "Accent.TButton",
            background="#304b6b",
            foreground="#ffffff",
            padding=(12, 8),
        )
        style.map(
            "Accent.TButton",
            background=[("active", "#3d628b"), ("pressed", "#263e59")],
        )

        style.configure(
            "Treeview",
            background="#12171d",
            fieldbackground="#12171d",
            foreground="#e7ebf2",
            rowheight=30,
            borderwidth=0,
            relief="flat",
        )
        style.map(
            "Treeview",
            background=[("selected", "#294b70")],
            foreground=[("selected", "#ffffff")],
        )
        style.configure(
            "Treeview.Heading",
            background="#202832",
            foreground="#ffffff",
            relief="flat",
            padding=7,
        )
        style.map(
            "Treeview.Heading",
            background=[("active", "#2b3541")],
            foreground=[("active", "#ffffff")],
        )

        style.configure(
            "TNotebook",
            background="#0f1318",
            borderwidth=0,
        )
        style.configure(
            "TNotebook.Tab",
            background="#1a2028",
            foreground="#aeb7c5",
            padding=(16, 9),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", "#29323e"), ("active", "#252e39")],
            foreground=[("selected", "#ffffff"), ("active", "#ffffff")],
        )

    def build_ui(self):
        header = tk.Frame(self, bg="#0b0e13", height=76)
        header.pack(fill="x")
        tk.Label(
            header,
            text="ByteRescue",
            bg="#0b0e13",
            fg="#ffffff",
            font=("Segoe UI", 23, "bold"),
        ).pack(side="left", padx=(24, 10), pady=16)
        tk.Label(
            header,
            text="Storage Analysis & Data Recovery",
            bg="#0b0e13",
            fg="#8f9aaa",
            font=("Segoe UI", 10),
        ).pack(side="left", pady=19)

        toolbar = tk.Frame(self, bg="#171c23")
        toolbar.pack(fill="x", padx=18, pady=(14, 8))

        self.buttons = []
        for label, command in [
            ("Refresh Drives", self.refresh_disks),
            ("Open Folder", self.open_folder),
            ("Analyze File", self.analyze_file),
            ("Hex Viewer", self.hex_view),
            ("Recover by Signature", self.recover_signature),
        ]:
            b = ttk.Button(toolbar, text=label, command=command)
            b.pack(side="left", padx=4)
            self.buttons.append(b)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=18, pady=8)

        self.analysis_tab = tk.Frame(self.notebook, bg="#171c23")
        self.help_tab = tk.Frame(self.notebook, bg="#171c23")
        self.notebook.add(self.analysis_tab, text="  Analysis  ")
        self.notebook.add(self.help_tab, text="  What am I looking at?  ")

        self.build_analysis_tab()
        self.build_help_tab()

        self.status = tk.StringVar(value="Ready")
        tk.Label(
            self,
            textvariable=self.status,
            anchor="w",
            bg="#0b0e13",
            fg="#8993a3",
            padx=18,
            pady=8,
        ).pack(fill="x")

    def build_analysis_tab(self):
        paned = tk.PanedWindow(
            self.analysis_tab,
            orient="horizontal",
            bg="#0f1318",
            sashwidth=5,
            borderwidth=0,
        )
        paned.pack(fill="both", expand=True, padx=4, pady=4)

        left = tk.Frame(paned, bg="#171c23")
        right = tk.Frame(paned, bg="#171c23")
        paned.add(left, minsize=380)
        paned.add(right, minsize=520)

        tk.Label(
            left,
            text="STORAGE DEVICES",
            bg="#171c23",
            fg="#8f9aaa",
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", padx=14, pady=(12, 8))

        self.drive_tree = ttk.Treeview(
            left,
            columns=("model", "size", "type", "status"),
            show="headings",
            selectmode="browse",
        )
        for c, title, width in [
            ("model", "Device", 230),
            ("size", "Capacity", 100),
            ("type", "Interface", 90),
            ("status", "Status", 90),
        ]:
            self.drive_tree.heading(c, text=title)
            self.drive_tree.column(c, width=width, anchor="w")
        self.drive_tree.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.drive_tree.bind("<<TreeviewSelect>>", self.drive_selected)

        tk.Label(
            right,
            text="ANALYSIS",
            bg="#171c23",
            fg="#8f9aaa",
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", padx=14, pady=(12, 8))

        self.info = tk.Text(
            right,
            bg="#0f1318",
            fg="#dce2eb",
            insertbackground="#ffffff",
            selectbackground="#294b70",
            selectforeground="#ffffff",
            relief="flat",
            font=("Consolas", 10),
            padx=14,
            pady=14,
            wrap="word",
        )
        self.info.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.info.insert(
            "1.0",
            "Welcome to ByteRescue.\n\n"
            "Select a storage device or use one of the tools above.\n\n"
            "For a simple explanation of each area, open the "
            "'What am I looking at?' tab.\n\n"
            "Safety: analysis does not intentionally write to the source drive.\n",
        )
        # Read-only: this panel displays results, it is not an editable
        # notepad. "disabled" still allows selecting and copying the text.
        self.info.configure(state="disabled")

    def build_help_tab(self):
        outer = tk.Frame(self.help_tab, bg="#171c23")
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(
            outer,
            bg="#171c23",
            highlightthickness=0,
            borderwidth=0,
        )
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        content = tk.Frame(canvas, bg="#171c23")

        window_id = canvas.create_window((0, 0), window=content, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        def resize(_event=None):
            canvas.itemconfigure(window_id, width=canvas.winfo_width())
            canvas.configure(scrollregion=canvas.bbox("all"))

        content.bind("<Configure>", resize)
        canvas.bind("<Configure>", resize)
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))

        canvas.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=10)
        scrollbar.pack(side="right", fill="y", padx=(0, 10), pady=10)

        tk.Label(
            content,
            text="What am I looking at?",
            bg="#171c23",
            fg="#ffffff",
            font=("Segoe UI", 20, "bold"),
        ).pack(anchor="w", padx=24, pady=(22, 4))

        tk.Label(
            content,
            text="A plain-English guide to the ByteRescue interface.",
            bg="#171c23",
            fg="#9da6b5",
            font=("Segoe UI", 10),
        ).pack(anchor="w", padx=24, pady=(0, 20))

        sections = [
            ("Storage Devices",
             "This is the list of physical storage devices Windows reports. "
             "A device can be an HDD, SATA SSD, NVMe SSD, USB drive, or another storage device."),
            ("Device / Model",
             "The manufacturer's model name reported by Windows. It helps you identify which physical drive you are working with."),
            ("Capacity",
             "The approximate total size of the physical device. Windows and drive manufacturers may display capacity differently because of unit conventions."),
            ("Interface",
             "How Windows reports the connection, such as SATA, USB, NVMe-related storage, or another interface."),
            ("Status",
             "The operating system's reported device status. This is not a complete hardware-health diagnosis."),
            ("Analysis",
             "This area shows information produced by the selected ByteRescue tool. It may contain device details, file information, hashes, or scan results."),
            ("Analyze File",
             "Select an individual file to see its size, modification time, path, and SHA-256 hash. SHA-256 is a fingerprint of the file's contents."),
            ("Hex Viewer",
             "Shows the raw bytes of a file as hexadecimal values and readable ASCII characters. This is useful for inspecting file headers and low-level data."),
            ("Recover by Signature",
             "Looks through a selected file or disk-image-like file for known byte patterns: JPEG, PNG, PDF, ZIP, GZIP, 7Z, "
             "WAV/AVI/WEBP (RIFF), SQLite, and FLAC. This is called file carving. It is a basic recovery method and can "
             "produce incomplete files. Recovered files are labeled 'verified' when the end of the file was confirmed from "
             "the format's own structure, or 'unverified' when it was only an estimate -- a matching signature never "
             "guarantees a complete, valid file."),
            ("Important: SSDs",
             "Deleted files on SSDs can become unrecoverable because of TRIM and the SSD controller's internal garbage collection. "
             "No recovery program can guarantee recovery after the underlying data has been discarded."),
            ("Safety",
             "When possible, work from a disk image instead of the original evidence drive. Always recover files to a different destination so you do not overwrite data you are trying to recover."),
        ]

        for title, body in sections:
            card = tk.Frame(
                content,
                bg="#202731",
                highlightbackground="#303a47",
                highlightthickness=1,
            )
            card.pack(fill="x", padx=24, pady=6)
            tk.Label(
                card,
                text=title,
                bg="#202731",
                fg="#ffffff",
                font=("Segoe UI", 11, "bold"),
                anchor="w",
            ).pack(fill="x", padx=14, pady=(12, 4))
            tk.Label(
                card,
                text=body,
                bg="#202731",
                fg="#c3cad5",
                font=("Segoe UI", 10),
                justify="left",
                anchor="w",
                wraplength=850,
            ).pack(fill="x", padx=14, pady=(0, 13))

    def set_status(self, text):
        self.status.set(text)

    def set_busy(self, busy):
        # Blocks starting a second scan/refresh while one is already running in the background thread.
        self._busy = busy
        state = "disabled" if busy else "normal"
        for b in self.buttons:
            try:
                b.configure(state=state)
            except tk.TclError:
                pass

    def safe_close(self):
        self.destroy()

    def refresh_disks(self):
        if self._busy:
            return
        for item in self.drive_tree.get_children():
            self.drive_tree.delete(item)

        ds = get_disks()
        if not ds:
            self.drive_tree.insert(
                "", "end",
                values=("No physical disks detected", "—", "—", "—")
            )
            self.set_status("No physical disks were returned by Windows.")
            return

        for d in ds:
            self.drive_tree.insert(
                "",
                "end",
                values=(
                    d.get("Model") or "Unknown device",
                    human(d.get("Size")),
                    d.get("InterfaceType") or "—",
                    d.get("Status") or "—",
                ),
                tags=(json.dumps(d, default=str),),  # full record, read back in drive_selected()
            )
        self.set_status(f"Detected {len(ds)} physical disk(s).")

    def drive_selected(self, _event=None):
        selected = self.drive_tree.selection()
        if not selected:
            return
        item = self.drive_tree.item(selected[0])
        raw = item.get("tags", [])
        if not raw:
            return
        try:
            obj = json.loads(raw[0])
            pretty = [
                "PHYSICAL DRIVE INFORMATION",
                "",
                f"Model:       {obj.get('Model') or 'Unknown'}",
                f"Disk Index:  {obj.get('Index') if obj.get('Index') is not None else '—'}",
                f"Interface:   {obj.get('InterfaceType') or '—'}",
                f"Media Type:  {obj.get('MediaType') or '—'}",
                f"Capacity:    {human(obj.get('Size'))}",
                f"Serial:      {obj.get('SerialNumber') or 'Unavailable'}",
                f"Status:      {obj.get('Status') or '—'}",
                "",
                "Use the What am I looking at? tab if any of these fields are unfamiliar.",
            ]
            self.show_text("\n".join(pretty))
            self.set_status("Physical drive information loaded.")
        except Exception as exc:
            self.show_error("Could not display the selected drive.", exc)

    def show_text(self, text):
        self.info.configure(state="normal")
        self.info.delete("1.0", "end")
        self.info.insert("1.0", text)
        self.info.configure(state="disabled")

    def choose_file(self):
        return filedialog.askopenfilename(
            title="Choose a file or disk image",
            filetypes=[
                ("All files", "*.*"),
                ("Disk images", "*.img *.dd *.raw *.bin"),
            ],
        )

    def open_folder(self):
        try:
            path = filedialog.askdirectory(title="Choose a folder to analyze")
            if not path:
                return
            self.path = Path(path)
            total = 0
            count = 0
            errors = 0
            for base, _, names in os.walk(path):
                for name in names:
                    try:
                        total += Path(base, name).stat().st_size
                        count += 1
                    except OSError:
                        errors += 1
            self.show_text(
                f"FOLDER ANALYSIS\n\n"
                f"Path: {path}\n\n"
                f"Files found: {count:,}\n"
                f"Total size: {human(total)}\n"
                f"Unreadable entries: {errors:,}\n\n"
                "This scan reads file metadata and does not modify the folder."
            )
            self.set_status(f"Folder analysis complete: {count:,} files.")
        except Exception as exc:
            self.show_error("Folder analysis failed.", exc)

    def analyze_file(self):
        path = self.choose_file()
        if not path:
            return
        try:
            p = Path(path)
            st = p.stat()
            digest = sha256(p)
            self.show_text(
                f"FILE ANALYSIS\n\n"
                f"Name:       {p.name}\n"
                f"Path:       {p}\n"
                f"Size:       {human(st.st_size)}\n"
                f"Modified:   {st.st_mtime}\n\n"
                f"SHA-256:\n{digest}\n\n"
                "SHA-256 is a content fingerprint. If two files have the same "
                "hash, their contents match with extremely high confidence."
            )
            self.set_status("File analysis complete.")
        except Exception as exc:
            self.show_error("File analysis failed.", exc)

    def hex_view(self):
        path = self.choose_file()
        if not path:
            return
        try:
            p = Path(path)
            with p.open("rb") as f:
                data = f.read(128 * 1024)  # bounded preview, not the whole file

            lines = []
            line_data = []  # Store raw byte data for each line
            for offset in range(0, len(data), 16):
                chunk = data[offset:offset + 16]
                line_data.append(chunk)
                hx = " ".join(f"{b:02X}" for b in chunk).ljust(47)
                asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
                lines.append(f"{offset:08X}  {hx}  {asc}")

            win = tk.Toplevel(self)
            win.title(f"ByteRescue — Hex Viewer — {p.name}")
            win.geometry("1200x780")
            win.configure(bg="#0f1318")
            win.transient(self)

            # Main container
            main_frame = tk.Frame(win, bg="#0f1318")
            main_frame.pack(fill="both", expand=True, padx=10, pady=10)

            # Top toolbar
            toolbar = tk.Frame(main_frame, bg="#171c23", height=50)
            toolbar.pack(fill="x", pady=(0, 8))

            # Search functionality
            tk.Label(toolbar, text="Search:", bg="#171c23", fg="#e7ebf2", font=("Segoe UI", 9)).pack(side="left", padx=(8, 4))
            search_var = tk.StringVar()
            search_entry = tk.Entry(toolbar, textvariable=search_var, bg="#0f1318", fg="#e7ebf2", 
                                   insertbackground="#ffffff", width=20, font=("Consolas", 9))
            search_entry.pack(side="left", padx=4)
            
            def search_hex():
                raw_term = search_var.get().strip().upper()
                if not raw_term:
                    return

                stripped = raw_term.replace(" ", "")
                if stripped and all(c in "0123456789ABCDEF" for c in stripped):
                    # Hex column always has a space between byte pairs, so re-insert them.
                    search_term = " ".join(stripped[i:i + 2] for i in range(0, len(stripped), 2))
                else:
                    # Not hex -- fall back to a literal text search (matches the ASCII column).
                    search_term = raw_term

                text_widget.tag_remove("found", "1.0", "end")
                found_count = 0
                search_index = "1.0"

                while True:
                    pos = text_widget.search(search_term, search_index, "end",
                                           nocase=True, regexp=False)
                    if not pos:
                        break

                    # Highlight the found text
                    end_pos = f"{pos}+{len(search_term)}c"
                    text_widget.tag_add("found", pos, end_pos)
                    text_widget.tag_configure("found", background="#3d628b", foreground="#ffffff")

                    search_index = end_pos
                    found_count += 1

                if found_count > 0:
                    text_widget.see("1.0")
                    status_var.set(f"Found {found_count} occurrence(s) of '{search_term}'")
                else:
                    status_var.set(f"'{search_term}' not found")

            search_btn = ttk.Button(toolbar, text="Search", command=search_hex)
            search_btn.pack(side="left", padx=4)

            # Hex code lookup
            tk.Label(toolbar, text="Lookup Hex:", bg="#171c23", fg="#e7ebf2", font=("Segoe UI", 9)).pack(side="left", padx=(12, 4))
            lookup_var = tk.StringVar()
            lookup_entry = tk.Entry(toolbar, textvariable=lookup_var, bg="#0f1318", fg="#e7ebf2",
                                  insertbackground="#ffffff", width=25, font=("Consolas", 9))
            lookup_entry.pack(side="left", padx=4)

            def lookup_hex():
                hex_code = lookup_var.get().strip().upper()
                if not hex_code:
                    lookup_result.config(text="Enter a hex code to lookup", fg="#687180")
                    return
                
                # Remove spaces and standardize
                hex_code = hex_code.replace(" ", "")
                
                # Try exact match first
                if hex_code in HEX_CODE_REFERENCE:
                    lookup_result.config(text=HEX_CODE_REFERENCE[hex_code], fg="#d7dde8")
                    return
                
                # Try with spaces
                spaced_hex = " ".join(hex_code[i:i+2] for i in range(0, len(hex_code), 2))
                if spaced_hex in HEX_CODE_REFERENCE:
                    lookup_result.config(text=HEX_CODE_REFERENCE[spaced_hex], fg="#d7dde8")
                    return
                
                # Try to find partial matches
                matches = []
                for key, value in HEX_CODE_REFERENCE.items():
                    if hex_code in key.replace(" ", "") or key.replace(" ", "") in hex_code:
                        matches.append(f"{key}: {value}")
                
                if matches:
                    lookup_result.config(text=f"Partial matches:\n" + "\n".join(matches[:3]), fg="#d7dde8")
                else:
                    lookup_result.config(text=f"Hex code '{hex_code}' not found in reference", fg="#e7a6a6")

            lookup_btn = ttk.Button(toolbar, text="Lookup", command=lookup_hex)
            lookup_btn.pack(side="left", padx=4)

            # Status variable
            status_var = tk.StringVar(value="Ready")

            # Paned window for hex viewer and info panel
            paned = tk.PanedWindow(main_frame, orient="vertical", bg="#0f1318", 
                                 sashwidth=5, borderwidth=0)
            paned.pack(fill="both", expand=True)

            # Hex viewer frame
            hex_frame = tk.Frame(paned, bg="#0f1318")
            paned.add(hex_frame, minsize=300)

            text = tk.Text(
                hex_frame,
                bg="#0a0d11",
                fg="#d7dde8",
                insertbackground="#ffffff",
                selectbackground="#294b70",
                font=("Consolas", 10),
                relief="flat",
                wrap="none",
                cursor="xterm",
            )
            ybar = ttk.Scrollbar(hex_frame, orient="vertical", command=text.yview)
            xbar = ttk.Scrollbar(hex_frame, orient="horizontal", command=text.xview)
            text.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
            text.grid(row=0, column=0, sticky="nsew")
            ybar.grid(row=0, column=1, sticky="ns")
            xbar.grid(row=1, column=0, sticky="ew")
            hex_frame.rowconfigure(0, weight=1)
            hex_frame.columnconfigure(0, weight=1)
            text.insert("1.0", "\n".join(lines))

            # Info panel frame
            info_frame = tk.Frame(paned, bg="#171c23", height=200)
            paned.add(info_frame, minsize=150)

            # Info panel header
            info_header = tk.Frame(info_frame, bg="#202832", height=30)
            info_header.pack(fill="x")
            tk.Label(info_header, text="Hex Code Information", bg="#202832", fg="#ffffff",
                    font=("Segoe UI", 9, "bold")).pack(side="left", padx=10, pady=5)

            # Lookup result display
            lookup_result = tk.Label(info_frame, text="Select a line or lookup a hex code",
                                   bg="#171c23", fg="#687180", font=("Segoe UI", 9),
                                   justify="left", anchor="nw", wraplength=1150)
            lookup_result.pack(fill="both", expand=True, padx=10, pady=8)

            # Reads bytes straight from line_data instead of re-parsing the
            # rendered line -- the ASCII column can contain spaces, which broke
            # a naive text split.
            def on_line_select(event):
                try:
                    # Get the line number where the user clicked
                    line_index = text.index(f"@{event.x},{event.y}")
                    line_num = int(line_index.split(".")[0])

                    # Get the line content (for display only)
                    line_content = text.get(f"{line_num}.0", f"{line_num}.end")

                    chunk_index = line_num - 1
                    if not (0 <= chunk_index < len(line_data)):
                        lookup_result.config(text=f"Line {line_num}: {line_content}", fg="#687180")
                        return

                    hex_bytes = line_data[chunk_index].hex().upper()

                    explanations = []

                    # Individual bytes anywhere in the row (control chars, etc.)
                    for i in range(0, len(hex_bytes), 2):
                        byte_pair = hex_bytes[i:i + 2]
                        if byte_pair in HEX_CODE_REFERENCE:
                            explanations.append(f"{byte_pair}: {HEX_CODE_REFERENCE[byte_pair]}")

                    # Multi-byte signatures anchored at the start of the row
                    for pattern_len in [4, 6, 8, 12, 16, 32]:
                        if len(hex_bytes) >= pattern_len:
                            pattern = hex_bytes[:pattern_len]
                            spaced_pattern = " ".join(pattern[i:i + 2] for i in range(0, len(pattern), 2))
                            if spaced_pattern in HEX_CODE_REFERENCE:
                                explanations.insert(0, f"{spaced_pattern}: {HEX_CODE_REFERENCE[spaced_pattern]}")

                    if explanations:
                        lookup_result.config(
                            text=f"Line {line_num}: {line_content}\n\nHex Code Meanings:\n" + "\n".join(explanations[:6]),
                            fg="#d7dde8",
                        )
                    else:
                        lookup_result.config(
                            text=(
                                f"Line {line_num}: {line_content}\n\n"
                                "No file signature or control-character meaning for the start of "
                                "this line. These look like common data bytes (text, padding, etc.) "
                                "-- common bytes are not evidence of a particular file format on "
                                "their own."
                            ),
                            fg="#687180",
                        )

                except Exception as e:
                    lookup_result.config(text=f"Error analyzing line: {e}", fg="#e7a6a6")

            text.bind("<Button-1>", on_line_select)

            # Configure text widget
            text.configure(state="disabled")
            
            # Bind Enter key for search
            search_entry.bind("<Return>", lambda e: search_hex())
            lookup_entry.bind("<Return>", lambda e: lookup_hex())

            # Status bar
            status_bar = tk.Label(main_frame, textvariable=status_var, bg="#0b0e13", fg="#8993a3",
                                anchor="w", padx=10, pady=5)
            status_bar.pack(fill="x", pady=(8, 0))

            self.set_status("Enhanced hex viewer opened with search and lookup features.")
        except Exception as exc:
            self.show_error("Hex viewer could not open the file.", exc)

    def recover_signature(self):
        if self._busy:
            return
        src = self.choose_file()
        if not src:
            return

        dst = filedialog.askdirectory(
            title="Choose a DIFFERENT recovery destination"
        )
        if not dst:
            return

        try:
            if Path(dst).resolve() == Path(src).resolve().parent:
                # Not necessarily unsafe, but strongly warn before recovering.
                if not messagebox.askyesno(
                    APP,
                    "The selected destination is the same folder as the source.\n\n"
                    "For safer recovery, choose a different drive or folder.\n\n"
                    "Continue anyway?",
                    icon="warning",
                ):
                    return
        except Exception:
            pass

        self.set_busy(True)
        self.set_status("Scanning signatures…")
        threading.Thread(
            target=self._scan_signatures,
            args=(Path(src), Path(dst)),
            daemon=True,
        ).start()

    def _scan_signatures(self, src, dst):
        # Read-only against src (mmap opened ACCESS_READ); output only ever goes to dst.
        try:
            size = src.stat().st_size
            if size == 0:
                self.after(0, lambda: self.scan_finished(0, 0, dst))
                return

            found = 0
            verified = 0
            WRITE_CHUNK = 4 * 1024 * 1024

            with src.open("rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as data:
                for name, (header, ext, kind) in SIGS.items():
                    pos = 0
                    while True:
                        i = data.find(header, pos)
                        if i < 0:
                            break

                        out_ext = ext
                        is_verified = False

                        if kind == "jpeg":
                            nxt = data.find(header, i + len(header))
                            result = _carve_footer_last(
                                data, i, len(header), b"\xff\xd9",
                                nxt if nxt >= 0 else None, JPEG_MAX_BYTES,
                            )
                            if result:
                                end, is_verified = result
                            else:
                                end = min(i + len(header) + JPEG_MAX_BYTES, len(data))

                        elif kind == "png":
                            footer = b"IEND\xaeB`\x82"
                            j = data.find(footer, i + len(header))
                            if j >= 0:
                                end = j + len(footer)
                                is_verified = True
                            else:
                                end = min(i + len(header) + UNVERIFIED_CAP_BYTES, len(data))

                        elif kind == "pdf":
                            nxt = data.find(header, i + len(header))
                            result = _carve_footer_last(
                                data, i, len(header), b"%%EOF",
                                nxt if nxt >= 0 else None, PDF_MAX_BYTES,
                            )
                            if result:
                                end, is_verified = result
                            else:
                                end = min(i + len(header) + PDF_MAX_BYTES, len(data))

                        elif kind == "zip":
                            result = _carve_zip(data, i)
                            if result:
                                end, is_verified = result
                            else:
                                nxt = data.find(header, i + len(header))
                                cap_end = nxt if nxt >= 0 else len(data)
                                end = min(cap_end, i + UNVERIFIED_CAP_BYTES, len(data))

                        elif kind == "riff":
                            result = _carve_riff(data, i)
                            end, out_ext, is_verified = result

                        elif kind == "sqlite":
                            result = _carve_sqlite(data, i)
                            if result:
                                end, is_verified = result
                            else:
                                end = min(i + UNVERIFIED_CAP_BYTES, len(data))

                        else:  # "capped": GZIP / 7Z / FLAC -- no reliable end marker exists
                            nxt = data.find(header, i + len(header))
                            cap_end = nxt if nxt >= 0 else len(data)
                            end = min(cap_end, i + UNVERIFIED_CAP_BYTES, len(data))

                        blob_len = end - i
                        if blob_len > 0:
                            found += 1
                            if is_verified:
                                verified += 1
                            tag = "" if is_verified else "_unverified"
                            out = dst / f"recovered_{found:05d}_{name.lower()}{tag}{out_ext}"
                            n = 2
                            while out.exists():
                                out = dst / f"recovered_{found:05d}_{name.lower()}{tag}_{n}{out_ext}"
                                n += 1
                            with open(out, "wb") as w:
                                # Write in chunks -- a verified carve can be large, avoid one giant bytes copy
                                p = i
                                while p < end:
                                    q = min(p + WRITE_CHUNK, end)
                                    w.write(data[p:q])
                                    p = q

                        # Skip past a verified carve's whole span so inner ZIP entries etc.
                        # don't each get re-matched as a separate "found" object.
                        pos = end if is_verified else i + len(header)

            self.after(0, lambda: self.scan_finished(found, verified, dst))
        except Exception as exc:
            self.after(0, lambda e=exc: self.scan_failed(e))

    def scan_finished(self, found, verified, dst):
        self.set_busy(False)
        unverified = found - verified
        self.set_status(
            f"Signature scan complete: {found} object(s) recovered "
            f"({verified} verified, {unverified} unverified)."
        )
        self.show_text(
            f"SIGNATURE RECOVERY COMPLETE\n\n"
            f"Objects recovered: {found}\n"
            f"  Verified (end offset structurally confirmed): {verified}\n"
            f"  Unverified (no reliable end marker -- cut off at a safety limit): {unverified}\n"
            f"Destination: {dst}\n\n"
            "This is a basic file-carving scanner, not proof of file validity. "
            "A matching signature only means the byte pattern was found -- it "
            "does not by itself mean the recovered bytes are a complete, "
            "undamaged file. Files with '_unverified' in their name had no "
            "reliable end marker and may be truncated or contain trailing "
            "unrelated data; open them with care."
        )

    def scan_failed(self, exc):
        self.set_busy(False)
        self.show_error("The recovery scan stopped because of an error.", exc)

    def show_error(self, title, exc):
        self.set_status("An error occurred.")
        messagebox.showerror(APP, f"{title}\n\n{type(exc).__name__}: {exc}")


def main():
    try:
        app = ByteRescue()
        app.mainloop()
    except Exception as exc:
        # Keep startup errors visible instead of silently returning to the prompt.
        try:
            messagebox.showerror(APP, f"ByteRescue could not start.\n\n{type(exc).__name__}: {exc}")
        except Exception:
            print(f"{APP} startup error: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
