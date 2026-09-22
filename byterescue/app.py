
import hashlib
import json
import os
import platform
import subprocess
import sys
import threading
import time
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

from . import applog
from .recovery import signatures, text_recovery
from .recovery.hex_reference import HEX_CODE_REFERENCE
from .recovery.scanner import RecoveryScan, destination_is_risky, export_report, is_device_path

APP = "ByteRescue"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


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


def get_physical_disk_media_types():
    # Win32_DiskDrive.MediaType is unreliable for SSD-vs-HDD (usually just
    # says "Fixed hard disk media" for both) -- Get-PhysicalDisk actually
    # distinguishes them. Best-effort match to Win32_DiskDrive's Index by
    # position; Windows numbers both the same way on typical single-
    # controller systems, but this is not guaranteed on every configuration.
    if platform.system() != "Windows":
        return {}
    script = r"""
Get-PhysicalDisk | Select-Object DeviceId,MediaType | ConvertTo-Json -Compress
"""
    out = powershell(script)
    if not out:
        return {}
    try:
        data = json.loads(out)
        rows = data if isinstance(data, list) else [data]
        return {str(r.get("DeviceId")): r.get("MediaType") for r in rows}
    except Exception:
        return {}


class SplashScreen:
    """Borderless, animated loading screen shown while the main window is
    built and the initial storage-device list is fetched -- a real
    PowerShell/WMI subprocess call (see get_disks()) that can take a
    second or more. The animation runs for as long as that actually takes,
    not a fixed fake delay; MIN_VISIBLE_MS only guards against a jarring
    flash-and-gone on a fast system, it never pads out real work.
    """

    MIN_VISIBLE_MS = 450

    def __init__(self, parent):
        self._start_time = time.monotonic()
        self._angle = 0
        self._closed = False
        self._animate_job = None

        self.win = tk.Toplevel(parent)
        self.win.overrideredirect(True)
        self.win.configure(bg="#304b6b")  # thin accent border via padding, see inner frame below
        self.win.attributes("-topmost", True)

        w, h = 420, 240
        self.win.update_idletasks()
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        self.win.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

        inner = tk.Frame(self.win, bg="#0b0e13")
        inner.pack(fill="both", expand=True, padx=1, pady=1)

        tk.Label(inner, text="ByteRescue", bg="#0b0e13", fg="#ffffff",
                 font=("Segoe UI", 22, "bold")).pack(pady=(38, 2))
        tk.Label(inner, text="Storage Analysis & Data Recovery", bg="#0b0e13",
                 fg="#8f9aaa", font=("Segoe UI", 10)).pack(pady=(0, 22))

        self.canvas = tk.Canvas(inner, width=36, height=36, bg="#0b0e13", highlightthickness=0)
        self.canvas.pack()
        self.arc = self.canvas.create_arc(3, 3, 33, 33, start=0, extent=100,
                                           style="arc", outline="#3d628b", width=3)

        self.status_var = tk.StringVar(value="Starting up...")
        tk.Label(inner, textvariable=self.status_var, bg="#0b0e13", fg="#687180",
                 font=("Segoe UI", 9)).pack(pady=(14, 0))

        self.win.update()
        self._animate()

    def _animate(self):
        if self._closed:
            return
        self._angle = (self._angle + 24) % 360
        self.canvas.itemconfigure(self.arc, start=self._angle)
        self._animate_job = self.win.after(40, self._animate)

    def set_status(self, text):
        if not self._closed:
            self.status_var.set(text)

    def finish(self, on_close):
        """Close once real startup work is done, waiting out any remainder
        of MIN_VISIBLE_MS first so the animation never just flickers by."""
        elapsed_ms = (time.monotonic() - self._start_time) * 1000
        remaining = int(self.MIN_VISIBLE_MS - elapsed_ms)
        if remaining > 0:
            self.win.after(remaining, lambda: self._close(on_close))
        else:
            self._close(on_close)

    def _close(self, on_close):
        self._closed = True
        # destroy() does NOT cancel an already-scheduled after() job against
        # this window -- without an explicit cancel, Tcl still tries to fire
        # it later and raises "invalid command name" against the now-gone
        # widget. _animate() itself checks self._closed too (belt and
        # braces for the case a callback was already in flight).
        if self._animate_job is not None:
            try:
                self.win.after_cancel(self._animate_job)
            except tk.TclError:
                pass
        try:
            self.win.destroy()
        except tk.TclError:
            pass
        on_close()


class ByteRescue(tk.Tk):
    def __init__(self):
        super().__init__()
        applog.install_tk_exception_logging(self)  # otherwise a callback error is invisible when launched without a console
        applog.get_logger().info("Main window constructing")
        self.withdraw()  # stays hidden behind the splash until startup finishes
        self.title("ByteRescue — Storage Analysis & Data Recovery")
        self.geometry("1220x760")
        self.minsize(1000, 650)
        self.configure(bg="#0f1318")
        self.path = None
        self._busy = False
        self.protocol("WM_DELETE_WINDOW", self.safe_close)

        self._splash = SplashScreen(self)
        # Deferred one tick so the splash actually paints before the
        # (fast, but nonzero) UI-construction work below runs.
        self.after(20, self._finish_construction)

    def _finish_construction(self):
        self.configure_styles()
        self.build_ui()
        self._splash.set_status("Detecting storage devices...")
        self._fetch_disks_async(self._finish_startup)

    def _finish_startup(self, disks):
        self._apply_disk_refresh(disks)
        self._splash.finish(on_close=self._reveal_main_window)

    def _reveal_main_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

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
            ("Recovery Center", self.recovery_center),
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
            ("Recovery Center",
             "Opens the recovery tool with four modes. 'Recover by Signature' searches for known byte patterns "
             "(JPEG, PNG, GIF, BMP, TIFF, ZIP, PDF, GZIP, 7Z, RAR, WAV/AVI/WEBP, SQLite, FLAC, MP3 tags, MP4/MOV, "
             "MKV/WebM, legacy Office, PE/EXE, ELF). 'Recover Text Files' looks for readable text instead, since "
             "plain text has no universal signature. 'Deep / Raw Scan' reads a file or drive in fixed-size chunks "
             "so very large sources don't need to fit in memory. 'Recover by File System' is a placeholder for "
             "future NTFS/FAT32/exFAT-aware recovery -- it is not implemented yet and says so when selected."),
            ("Verified vs. unverified",
             "Each recovery result is 'verified' when its end offset was proven from the format's own structure "
             "(an exact length field, a checksummed footer, or a fully walked container), or 'unverified' when no "
             "reliable end marker exists and a safety cap was used instead. A matching signature never guarantees "
             "a complete, undamaged file -- check the Validation column too."),
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

    def _fetch_disks_async(self, on_done):
        # get_disks() shells out to PowerShell/WMI and can take a second or
        # more -- run it off the main thread so the GUI (and the startup
        # splash's animation) never freezes while it's in flight.
        def worker():
            disks = get_disks()
            self.after(0, lambda: on_done(disks))
        threading.Thread(target=worker, daemon=True).start()

    def refresh_disks(self):
        if self._busy:
            return
        self.set_busy(True)
        self.set_status("Detecting storage devices...")
        self._fetch_disks_async(self._apply_disk_refresh)

    def _apply_disk_refresh(self, ds):
        self.set_busy(False)
        for item in self.drive_tree.get_children():
            self.drive_tree.delete(item)

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

    def hex_view(self, path=None, focus_offset=None, highlight_length=None):
        # focus_offset/highlight_length let a Recovery Center result open the
        # viewer scrolled to and highlighting its own signature match; the
        # toolbar button calls this with neither, unchanged from before.
        if path is None:
            path = self.choose_file()
            if not path:
                return
        try:
            # A recovery result on a physical-drive source passes a raw
            # \\.\PhysicalDriveN string -- must NOT go through Path(), which
            # mangles it (see recovery.scanner.is_device_path()). Keep it a
            # plain str in that case; open()/seek()/read() work on either.
            device_source = is_device_path(path)
            display_name = path if device_source else Path(path).name
            window_size = 128 * 1024
            if focus_offset is not None:
                window_start = max(0, focus_offset - 4096)
            else:
                window_start = 0
            with open(path, "rb") as f:
                f.seek(window_start)
                data = f.read(window_size)  # bounded preview, not the whole file

            lines = []
            line_data = []  # Store raw byte data for each line
            focus_line = None
            for local_offset in range(0, len(data), 16):
                abs_offset = window_start + local_offset
                chunk = data[local_offset:local_offset + 16]
                line_data.append(chunk)
                hx = " ".join(f"{b:02X}" for b in chunk).ljust(47)
                asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
                lines.append(f"{abs_offset:08X}  {hx}  {asc}")
                if focus_offset is not None and focus_line is None and abs_offset + 16 > focus_offset:
                    focus_line = len(lines)  # 1-indexed, matches Tk Text line numbering

            win = tk.Toplevel(self)
            win.title(f"ByteRescue — Hex Viewer — {display_name}")
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
            text_widget = text  # search_hex() below refers to this name

            if focus_line is not None:
                # Jump to and highlight the bytes a Recovery Center result pointed at.
                text_widget.see(f"{focus_line}.0")
                line_abs_offset = window_start + (focus_line - 1) * 16
                local_byte = focus_offset - line_abs_offset
                length = min(highlight_length or 1, 16 - local_byte)
                hex_col = 10 + local_byte * 3
                end_col = hex_col + length * 3 - 1
                text_widget.tag_add("focus", f"{focus_line}.{hex_col}", f"{focus_line}.{end_col}")
                text_widget.tag_configure("focus", background="#a3742a", foreground="#ffffff")

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

            self.set_status("Hex viewer opened (read-only -- never writes back to the source file).")
        except Exception as exc:
            self.show_error("Hex viewer could not open the file.", exc)

    def recovery_center(self):
        if self._busy:
            return
        RecoveryCenter(self)

    def show_error(self, title, exc):
        self.set_status("An error occurred.")
        messagebox.showerror(APP, f"{title}\n\n{type(exc).__name__}: {exc}")


MODE_SIGNATURE = "Recover by Signature"
MODE_TEXT = "Recover Text Files"
MODE_FILESYSTEM = "Recover by File System"
MODE_DEEP = "Deep / Raw Scan"

FORMAT_LABELS = {
    "JPEG": "JPEG (.jpg)", "PNG": "PNG", "PDF": "PDF", "ZIP": "ZIP / Office (.docx etc.)",
    "GZIP": "GZIP (.gz)", "7Z": "7-Zip", "FLAC": "FLAC", "RIFF": "WAV / AVI / WebP (RIFF)",
    "SQLITE": "SQLite database", "BMP": "BMP", "GIF": "GIF", "TIFF": "TIFF", "RAR": "RAR",
    "OLE": "Legacy Office (.doc/.xls/.ppt)", "MKV": "MKV / WebM", "MP3_ID3": "MP3 (ID3 tag only)",
    "PE": "Windows PE (.exe/.dll)", "ELF": "ELF (Linux executable)", "MP4": "MP4 / MOV",
}


class RecoveryCenter(tk.Toplevel):
    """The recovery UI: mode/source/format selection, scan controls with
    pause/resume/cancel and live progress, a results table, and actions
    (preview, recover, export report, jump to Hex Viewer). Kept as its own
    class -- app.py's ByteRescue class only opens it -- so this file stays
    navigable instead of one more giant method bolted onto the main window.
    All actual carving/text-detection/scanning logic lives in
    byterescue.recovery; this class is GUI plumbing only.
    """

    BG = "#0f1318"
    PANEL = "#171c23"
    CARD = "#202731"
    BORDER = "#303a47"
    TEXT = "#e7ebf2"
    MUTED = "#8f9aaa"
    WARN = "#e7c56a"
    DANGER = "#e7a6a6"
    OK = "#8fd19e"

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("ByteRescue — Recovery Center")
        self.geometry("1280x860")
        self.minsize(1080, 700)
        self.configure(bg=self.BG)
        self.transient(app)

        self.scan = None
        self._scan_running = False  # separate from `self.scan is None`: scan stays set
        # after completion so Preview/Recover Selected/etc keep working on its results.
        self.last_log = None
        self._paused = False
        self._row_count = 0  # how many scan.results have been inserted into the tree so far
        self._progress_determinate = True

        self.mode_var = tk.StringVar(value=MODE_SIGNATURE)
        self.source_kind_var = tk.StringVar(value="file")
        self.source_path_var = tk.StringVar(value="(none selected)")
        self.drive_choice_var = tk.StringVar()
        self.dest_var = tk.StringVar(value="(none selected)")
        self.min_text_len_var = tk.IntVar(value=text_recovery.DEFAULT_MIN_LENGTH)
        self.scan_area_var = tk.StringVar(value="Whole File")
        self.status_var = tk.StringVar(value="Choose a mode, source, and destination, then start.")
        self.progress_var = tk.StringVar(value="")
        self.summary_var = tk.StringVar(value="Found: 0   Validated: 0   Partial: 0   Rejected: 0")
        self.ssd_warning_var = tk.StringVar(value="")

        self._chosen_file_path = None
        self._drives = []  # list of raw disk dicts from get_disks()
        self.format_vars = {name: tk.BooleanVar(value=True) for name in signatures.SIGNATURES}

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._on_mode_change()
        self._on_source_kind_change()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _card(self, parent, title):
        card = tk.Frame(parent, bg=self.CARD, highlightbackground=self.BORDER, highlightthickness=1)
        tk.Label(card, text=title, bg=self.CARD, fg=self.TEXT, font=("Segoe UI", 10, "bold"),
                 anchor="w").pack(fill="x", padx=12, pady=(10, 6))
        return card

    def _build_ui(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)

        recovery_tab = tk.Frame(self.notebook, bg=self.BG)
        help_tab = tk.Frame(self.notebook, bg=self.BG)
        self.notebook.add(recovery_tab, text="  Recovery  ")
        self.notebook.add(help_tab, text="  Help / Docs  ")

        outer = tk.Frame(recovery_tab, bg=self.BG)
        outer.pack(fill="both", expand=True, padx=12, pady=12)

        top = tk.Frame(outer, bg=self.BG)
        top.pack(fill="x")

        self._build_setup_card(top)
        self._build_progress_card(outer)
        self._build_results_card(outer)

        self._build_help_tab(help_tab)

        tk.Label(self, textvariable=self.status_var, bg="#0b0e13", fg=self.MUTED,
                 anchor="w", padx=14, pady=6).pack(fill="x", side="bottom")

    def _build_help_tab(self, parent):
        outer = tk.Frame(parent, bg=self.BG)
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, bg=self.BG, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        content = tk.Frame(canvas, bg=self.BG)

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

        tk.Label(content, text="Using the Recovery Center", bg=self.BG, fg="#ffffff",
                 font=("Segoe UI", 18, "bold")).pack(anchor="w", padx=20, pady=(18, 4))
        tk.Label(content, text="What each control does, and what the results actually mean.",
                 bg=self.BG, fg=self.MUTED, font=("Segoe UI", 10)).pack(anchor="w", padx=20, pady=(0, 16))

        sections = [
            ("1. Pick a Recovery Mode",
             "Recover by Signature searches for known byte patterns (JPEG, PNG, ZIP, PDF, and the rest of "
             "the list in File Types) -- fast and works on almost any source, but a signature match is not "
             "proof of a complete file. Recover Text Files looks for long runs of plausible readable text "
             "(ASCII/UTF-8/UTF-16) instead, since plain text has no magic header to search for. Deep / Raw "
             "Scan runs the same signature search as mode 1, but reads the source in fixed-size chunks "
             "instead of loading it all at once -- use it for very large sources or a physical drive. "
             "Recover by File System reads the volume's actual FAT12/16/32 directory table, including "
             "deleted entries, which can recover files the other three modes miss entirely -- but it only "
             "supports FAT12/16/32; NTFS and exFAT are not implemented and will report a clear error."),
            ("2. Choose a Source",
             "You can't 'select the deleted file' here -- it's deleted, so no file picker on Windows can "
             "show it to you. What you pick here is the CONTAINER to search: File / Disk Image opens a "
             "standard file picker for a real file that still exists, or a raw disk image (.img/.dd/.raw/"
             ".bin) if you already made one. Physical Drive lists the drives Windows detects and reads "
             "the raw device directly; this needs ByteRescue to be run as Administrator, is strictly "
             "read-only, and shows a TRIM warning automatically when the selected drive reports as SSD/"
             "NVMe -- TRIM can make deleted data permanently unrecoverable, and nothing can undo that "
             "once it has happened. Either way, run a scan (Start Recovery Scan below) and the deleted "
             "file -- if it's still recoverable -- will show up as its own row in Recovery Results, which "
             "is where you actually select and recover it from."),
            ("3. File Types / text options",
             "For signature modes, uncheck anything you don't want to search for -- fewer types means a "
             "faster scan. For Recover Text Files, 'Minimum text run length' sets how many consecutive "
             "readable bytes are needed before something counts as 'probably text' -- raise it to cut down "
             "on short, low-confidence fragments; lower it to catch short files."),
            ("4. Destination",
             "Always a separate folder from the source. If the folder you pick looks like it could be on "
             "the source drive itself, ByteRescue warns before starting -- writing recovered data back to "
             "the drive you're recovering from can overwrite the very data you're trying to get back."),
            ("5. Scan Progress",
             "Shows live offset/bytes-scanned/speed/ETA (or a directory-entry count for Recover by File "
             "System, which doesn't have a meaningful byte-percentage) plus how many candidates have been "
             "found, accepted as valid, and rejected. Pause suspends the scan in place; Stop cancels it -- "
             "results found before stopping are kept."),
            ("6. Reading the Results table",
             "Offset is where the item starts in the source. Confidence is High/Medium/Low, not a "
             "percentage guarantee. Validation comes from actually trying to parse the recovered bytes "
             "(Passed/Partial/Failed/Unknown) -- it is a separate, independent check from Confidence. "
             "Status explains anything unusual in plain language, including the file-system mode's "
             "contiguous-allocation assumption for a fragmented deleted file. A filename in the results "
             "with '_unverified' means no reliable end-of-file marker was found and a safety limit was "
             "used instead -- treat that recovered file as a guess, not a confirmed result."),
            ("7. Preview / Recover Selected / View in Hex Viewer / Export Report",
             "Preview shows an item's details (and, for text results, the actual matched text) without "
             "saving anything. Recover Selected writes the selected row(s) to your destination folder -- "
             "nothing is ever written until you do this. View in Hex Viewer opens the source in the Hex "
             "Viewer scrolled to, and highlighting, that item's exact offset -- useful for sanity-checking "
             "a result yourself. Export Report saves everything found (metadata only -- offsets, sizes, "
             "hashes, validation results, never recovered file contents) as a JSON file you can keep or share."),
            ("Safety, in one paragraph",
             "ByteRescue never writes to the source during scanning, in any mode, on any source. Recovered "
             "files only ever go to the destination folder you explicitly choose. SSD/NVMe TRIM, "
             "encryption, and genuine overwriting are all things no software can undo -- a clean scan with "
             "zero results usually means the data is actually gone, not that ByteRescue failed to look."),
        ]

        for title, body in sections:
            card = tk.Frame(content, bg=self.CARD, highlightbackground=self.BORDER, highlightthickness=1)
            card.pack(fill="x", padx=20, pady=6)
            tk.Label(card, text=title, bg=self.CARD, fg="#ffffff", font=("Segoe UI", 11, "bold"),
                     anchor="w").pack(fill="x", padx=14, pady=(12, 4))
            tk.Label(card, text=body, bg=self.CARD, fg="#c3cad5", font=("Segoe UI", 10),
                     justify="left", anchor="w", wraplength=900).pack(fill="x", padx=14, pady=(0, 13))

    def _build_setup_card(self, parent):
        card = self._card(parent, "RECOVERY")
        card.pack(fill="x", pady=(0, 10))
        body = tk.Frame(card, bg=self.CARD)
        body.pack(fill="x", padx=12, pady=(0, 10))

        row1 = tk.Frame(body, bg=self.CARD)
        row1.pack(fill="x", pady=4)
        tk.Label(row1, text="Recovery Mode:", bg=self.CARD, fg=self.TEXT, width=16, anchor="w").pack(side="left")
        mode_box = ttk.Combobox(
            row1, textvariable=self.mode_var, state="readonly", width=26,
            values=[MODE_SIGNATURE, MODE_TEXT, MODE_FILESYSTEM, MODE_DEEP],
        )
        mode_box.pack(side="left", padx=(0, 16))
        mode_box.bind("<<ComboboxSelected>>", lambda e: self._on_mode_change())

        tk.Label(row1, text="Scan Area:", bg=self.CARD, fg=self.TEXT, anchor="w").pack(side="left")
        self.scan_area_box = ttk.Combobox(
            row1, textvariable=self.scan_area_var, state="disabled", width=16, values=["Whole File"],
        )
        self.scan_area_box.pack(side="left", padx=(6, 0))

        row2 = tk.Frame(body, bg=self.CARD)
        row2.pack(fill="x", pady=4)
        tk.Label(row2, text="Source:", bg=self.CARD, fg=self.TEXT, width=16, anchor="w").pack(side="left")
        ttk.Radiobutton(row2, text="File / Disk Image", value="file", variable=self.source_kind_var,
                         command=self._on_source_kind_change).pack(side="left")
        ttk.Radiobutton(row2, text="Physical Drive", value="drive", variable=self.source_kind_var,
                         command=self._on_source_kind_change).pack(side="left", padx=(10, 0))

        row3 = tk.Frame(body, bg=self.CARD)
        row3.pack(fill="x", pady=4)
        self.file_source_frame = tk.Frame(row3, bg=self.CARD)
        ttk.Button(self.file_source_frame, text="Choose File / Disk Image...",
                   command=self._choose_source_file).pack(side="left")
        tk.Label(self.file_source_frame, textvariable=self.source_path_var, bg=self.CARD,
                 fg=self.MUTED, anchor="w").pack(side="left", padx=10)

        self.drive_source_frame = tk.Frame(row3, bg=self.CARD)
        self.drive_box = ttk.Combobox(self.drive_source_frame, textvariable=self.drive_choice_var,
                                       state="readonly", width=60)
        self.drive_box.pack(side="left")
        self.drive_box.bind("<<ComboboxSelected>>", lambda e: self._on_drive_selected())
        ttk.Button(self.drive_source_frame, text="Refresh",
                   command=self._refresh_drive_list).pack(side="left", padx=(8, 0))
        self.file_source_frame.pack(side="left")

        tk.Label(
            body,
            text="Select the DRIVE (or a disk-image file of one) to scan here -- not the deleted file "
                 "itself. A deleted file won't appear in any file picker; it shows up as a row in "
                 "Recovery Results once you run a scan below, and you recover it from there.",
            bg=self.CARD, fg=self.MUTED, wraplength=1100, justify="left", anchor="w",
        ).pack(fill="x", pady=(0, 2))

        self.row_warn = tk.Frame(body, bg=self.CARD)
        self.row_warn.pack(fill="x", pady=(2, 4))
        tk.Label(self.row_warn, textvariable=self.ssd_warning_var, bg=self.CARD, fg=self.WARN,
                 anchor="w", wraplength=1100, justify="left").pack(fill="x")

        # types_frame/text_frame/fs_frame are packed (mutually exclusively) by
        # _on_mode_change, not here -- their pack() calls all use after=self.row_warn
        # so whichever one is visible lands in the same spot regardless of order created.
        self.types_frame = tk.Frame(body, bg=self.CARD)
        tk.Label(self.types_frame, text="File Types:", bg=self.CARD, fg=self.TEXT,
                 anchor="w").pack(side="left", anchor="n", padx=(0, 8))
        grid = tk.Frame(self.types_frame, bg=self.CARD)
        grid.pack(side="left", fill="x", expand=True)
        cols = 4
        for idx, name in enumerate(signatures.SIGNATURES):
            cb = tk.Checkbutton(
                grid, text=FORMAT_LABELS.get(name, name), variable=self.format_vars[name],
                bg=self.CARD, fg=self.TEXT, selectcolor="#12171d", activebackground=self.CARD,
                activeforeground=self.TEXT, anchor="w",
            )
            cb.grid(row=idx // cols, column=idx % cols, sticky="w", padx=4, pady=1)
        btns = tk.Frame(self.types_frame, bg=self.CARD)
        btns.pack(side="left", anchor="n", padx=(12, 0))
        ttk.Button(btns, text="All", width=6, command=lambda: self._set_all_formats(True)).pack(pady=1)
        ttk.Button(btns, text="None", width=6, command=lambda: self._set_all_formats(False)).pack(pady=1)

        self.text_frame = tk.Frame(body, bg=self.CARD)
        tk.Label(self.text_frame, text="Minimum text run length (bytes):", bg=self.CARD, fg=self.TEXT,
                 anchor="w").pack(side="left")
        tk.Spinbox(self.text_frame, from_=20, to=5000, increment=10, width=8,
                   textvariable=self.min_text_len_var, bg="#12171d", fg=self.TEXT,
                   insertbackground="#ffffff", buttonbackground=self.CARD).pack(side="left", padx=8)
        tk.Label(
            self.text_frame,
            text="Text files usually do not have a unique file signature. ByteRescue searches for "
                 "readable text patterns instead of relying on a traditional magic header.",
            bg=self.CARD, fg=self.MUTED, wraplength=700, justify="left", anchor="w",
        ).pack(side="left", padx=8)

        self.fs_frame = tk.Frame(body, bg=self.CARD)
        tk.Label(
            self.fs_frame,
            text="Reads the volume's actual FAT12/16/32 directory entries (including deleted ones) "
                 "instead of searching for byte signatures. Recovers a deleted file's name and content "
                 "when its cluster(s) haven't been overwritten yet -- but FAT deletion normally erases "
                 "the file's cluster CHAIN, not just the directory entry, so a deleted file spanning "
                 "more than one cluster is recovered by ASSUMING it was stored contiguously; if it was "
                 "fragmented on disk, only its first cluster's worth of data will be correct (this is "
                 "labeled per result, not hidden). NTFS and exFAT are NOT implemented -- scanning one of "
                 "those will report a clear error instead of silently finding nothing.",
            bg=self.CARD, fg=self.WARN, wraplength=1100, justify="left", anchor="w",
        ).pack(fill="x")

        row_dst = tk.Frame(body, bg=self.CARD)
        row_dst.pack(fill="x", pady=(8, 4))
        tk.Label(row_dst, text="Destination:", bg=self.CARD, fg=self.TEXT, width=16, anchor="w").pack(side="left")
        ttk.Button(row_dst, text="Choose Folder...", command=self._choose_destination).pack(side="left")
        tk.Label(row_dst, textvariable=self.dest_var, bg=self.CARD, fg=self.MUTED, anchor="w").pack(
            side="left", padx=10)

        tk.Label(
            body,
            text="IMPORTANT: recover files to a different physical drive whenever possible. Writing "
                 "recovered data to the source drive may overwrite recoverable data. ByteRescue never "
                 "writes to the source during scanning -- recovered files only ever go to the destination "
                 "you choose here.",
            bg=self.CARD, fg=self.MUTED, wraplength=1100, justify="left", anchor="w",
        ).pack(fill="x", pady=(4, 8))

        self.start_btn = ttk.Button(body, text="START RECOVERY SCAN", style="Accent.TButton",
                                     command=self._start_scan)
        self.start_btn.pack(anchor="w")

    def _build_progress_card(self, parent):
        card = self._card(parent, "SCAN PROGRESS")
        card.pack(fill="x", pady=(0, 10))
        body = tk.Frame(card, bg=self.CARD)
        body.pack(fill="x", padx=12, pady=(0, 10))

        self.progress_bar = ttk.Progressbar(body, mode="determinate")
        self.progress_bar.pack(fill="x", pady=(0, 6))

        tk.Label(body, textvariable=self.progress_var, bg=self.CARD, fg=self.TEXT,
                 anchor="w", justify="left", font=("Consolas", 9)).pack(fill="x")

        controls = tk.Frame(body, bg=self.CARD)
        controls.pack(fill="x", pady=(6, 0))
        self.pause_btn = ttk.Button(controls, text="Pause", command=self._toggle_pause, state="disabled")
        self.pause_btn.pack(side="left")
        self.stop_btn = ttk.Button(controls, text="Stop", command=self._stop_scan, state="disabled")
        self.stop_btn.pack(side="left", padx=(6, 0))

    def _build_results_card(self, parent):
        card = self._card(parent, "RECOVERY RESULTS")
        card.pack(fill="both", expand=True)
        body = tk.Frame(card, bg=self.CARD)
        body.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        tk.Label(body, textvariable=self.summary_var, bg=self.CARD, fg=self.TEXT,
                 anchor="w").pack(fill="x", pady=(0, 6))

        columns = ("type", "ext", "offset", "size", "confidence", "validation", "status")
        self.tree = ttk.Treeview(body, columns=columns, show="headings", selectmode="extended", height=12)
        headings = [
            ("type", "Type", 90), ("ext", "Ext", 60), ("offset", "Offset", 110),
            ("size", "Size", 90), ("confidence", "Confidence", 90),
            ("validation", "Validation", 90), ("status", "Status", 260),
        ]
        for col, text, width in headings:
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True, side="left")
        ybar = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        ybar.pack(side="left", fill="y")
        self.tree.configure(yscrollcommand=ybar.set)

        actions = tk.Frame(card, bg=self.CARD)
        actions.pack(fill="x", padx=12, pady=(0, 10))
        ttk.Button(actions, text="Preview", command=self._on_preview).pack(side="left")
        ttk.Button(actions, text="Recover Selected", command=self._on_recover_selected).pack(side="left", padx=6)
        ttk.Button(actions, text="View in Hex Viewer", command=self._on_view_hex).pack(side="left")
        ttk.Button(actions, text="Export Report", command=self._on_export_report).pack(side="left", padx=6)
        ttk.Button(actions, text="Open Log", command=self._on_open_log).pack(side="left")

    # ------------------------------------------------------------------
    # Mode / source selection
    # ------------------------------------------------------------------

    def _set_all_formats(self, value):
        for var in self.format_vars.values():
            var.set(value)

    def _on_mode_change(self):
        mode = self.mode_var.get()
        for f in (self.types_frame, self.text_frame, self.fs_frame):
            f.pack_forget()
        if mode in (MODE_SIGNATURE, MODE_DEEP):
            self.types_frame.pack(fill="x", pady=(4, 4), after=self.row_warn)
        elif mode == MODE_TEXT:
            self.text_frame.pack(fill="x", pady=(4, 4), after=self.row_warn)
        elif mode == MODE_FILESYSTEM:
            self.fs_frame.pack(fill="x", pady=(4, 4), after=self.row_warn)
        self.start_btn.configure(state="normal")

    def _on_source_kind_change(self):
        kind = self.source_kind_var.get()
        if kind == "file":
            self.drive_source_frame.pack_forget()
            self.file_source_frame.pack(side="left")
            self.scan_area_box.configure(values=["Whole File"])
            self.scan_area_var.set("Whole File")
            self.ssd_warning_var.set("")
        else:
            self.file_source_frame.pack_forget()
            self.drive_source_frame.pack(side="left")
            self.scan_area_box.configure(values=["Entire Device"])
            self.scan_area_var.set("Entire Device")
            self._refresh_drive_list()

    def _choose_source_file(self):
        path = self.app.choose_file()
        if not path:
            return
        self._chosen_file_path = Path(path)
        self.source_path_var.set(str(self._chosen_file_path))

    def _refresh_drive_list(self):
        self._drives = get_disks()
        media_types = get_physical_disk_media_types()
        labels = []
        for d in self._drives:
            idx = d.get("Index")
            media = media_types.get(str(idx), "")
            labels.append(f"Disk {idx}: {d.get('Model') or 'Unknown'} ({human(d.get('Size'))}) {('[' + media + ']') if media else ''}".strip())
        self.drive_box.configure(values=labels)
        if labels:
            self.drive_box.current(0)
            self._on_drive_selected()
        else:
            self.drive_choice_var.set("")
            self.ssd_warning_var.set("No physical disks were returned by Windows.")

    def _on_drive_selected(self):
        i = self.drive_box.current()
        if i < 0 or i >= len(self._drives):
            return
        d = self._drives[i]
        media_types = get_physical_disk_media_types()
        media = (media_types.get(str(d.get("Index"))) or "").upper()
        base = (
            "Physical-drive scanning opens the raw device path (\\\\.\\PhysicalDriveN). This requires "
            "running ByteRescue as Administrator, is strictly read-only, and has not been verified against "
            "real hardware in this build -- if it fails, it will report an error rather than modify the drive."
        )
        if media in ("SSD", "SCM"):
            self.ssd_warning_var.set(
                "SSD/NVMe detected. Deleted data may have been removed by TRIM/garbage collection and may "
                "no longer be recoverable. ByteRescue cannot bypass TRIM.\n" + base
            )
        else:
            self.ssd_warning_var.set(base)

    def _choose_destination(self):
        path = filedialog.askdirectory(title="Choose a recovery destination")
        if not path:
            return
        self.dest_var.set(path)

    # ------------------------------------------------------------------
    # Scan lifecycle
    # ------------------------------------------------------------------

    def _current_source(self):
        if self.source_kind_var.get() == "file":
            return self._chosen_file_path, self._chosen_file_path.name if self._chosen_file_path else None
        i = self.drive_box.current()
        if i < 0 or i >= len(self._drives):
            return None, None
        idx = self._drives[i].get("Index")
        label = f"Physical Drive {idx}: {self._drives[i].get('Model') or 'Unknown'}"
        # Deliberately a plain str, NOT Path(...): pathlib parses \\.\PhysicalDriveN
        # as a UNC path and str()'s it back out with a trailing backslash, which
        # Windows then refuses to open. See recovery.scanner.is_device_path().
        return rf"\\.\PhysicalDrive{idx}", label

    def _start_scan(self):
        if self.app._busy or self._scan_running:
            return
        mode = self.mode_var.get()

        source_path, source_label = self._current_source()
        if not source_path:
            messagebox.showwarning(APP, "Choose a source file or physical drive first.")
            return
        dest = self.dest_var.get()
        if dest == "(none selected)" or not dest:
            messagebox.showwarning(APP, "Choose a recovery destination first.")
            return
        dest_path = Path(dest)

        if mode == MODE_FILESYSTEM:
            engine_mode = "filesystem"
        elif mode == MODE_TEXT:
            engine_mode = "text"
        else:
            engine_mode = "signature"
        selected_formats = [n for n, v in self.format_vars.items() if v.get()]
        if engine_mode == "signature" and not selected_formats:
            messagebox.showwarning(APP, "Select at least one file type to search for.")
            return

        if destination_is_risky(source_path, dest_path):
            if not messagebox.askyesno(
                APP,
                "IMPORTANT: the destination you chose looks like it could be on the source drive itself.\n\n"
                "Writing recovered data to the source may overwrite the very data you are trying to "
                "recover. Choose a different physical drive whenever possible.\n\n"
                "Continue anyway?",
                icon="warning",
            ):
                return

        use_chunked = (mode == MODE_DEEP) or (self.source_kind_var.get() == "drive")

        if engine_mode == "filesystem":
            total_known = False  # progress is a directory-entry count, not a byte-size percentage
        elif is_device_path(source_path):
            total_known = False  # stat() "succeeds" on a device path but always reports size 0
        else:
            try:
                total_known = os.stat(source_path).st_size > 0
            except OSError:
                total_known = False

        self.tree.delete(*self.tree.get_children())
        self._row_count = 0
        self.last_log = None
        self.progress_bar.stop()
        self._progress_determinate = total_known
        self.progress_bar.configure(mode="determinate" if total_known else "indeterminate", value=0)
        if not total_known:
            self.progress_bar.start(50)

        self.scan = RecoveryScan(
            source_path, dest_path, mode=engine_mode, selected_formats=selected_formats,
            use_chunked=use_chunked, min_text_length=self.min_text_len_var.get(),
            progress_cb=self._on_progress, source_label=source_label,
        )
        applog.get_logger().info(
            "Scan starting: mode=%s engine_mode=%s source=%r dest=%r use_chunked=%s formats=%s",
            mode, engine_mode, str(source_path), str(dest_path), use_chunked, selected_formats,
        )
        self._scan_running = True
        self._paused = False
        self.pause_btn.configure(text="Pause", state="normal")
        self.stop_btn.configure(state="normal")
        self.start_btn.configure(state="disabled")
        self.status_var.set(f"Scanning {source_label}...")
        self.app.set_busy(True)

        threading.Thread(target=self._run_scan, daemon=True, name="ByteRescue-scan").start()

    def _run_scan(self):
        try:
            log = self.scan.run()
        except Exception:
            applog.log_exception("recovery scan background thread")
            log = {"status": "error", "found": 0, "valid": 0, "rejected": 0,
                   "errors": ["The scan thread crashed unexpectedly -- see the log file for details."]}
        self.after(0, lambda: self._on_scan_done(log))

    def _on_progress(self, info):
        # Called from the scanner's background thread -- marshal onto the Tk main thread.
        self.after(0, lambda info=info: self._apply_progress(info))

    def _apply_progress(self, info):
        scanned = info.get("bytes_scanned", 0)
        total = info.get("total_bytes")
        speed = info.get("speed_bytes_s", 0)
        eta = info.get("eta_seconds")
        is_entries = info.get("unit") == "entries"  # filesystem mode counts directory entries, not bytes

        if is_entries:
            line1 = f"Directory entries scanned: {scanned:,}"
            line2 = f"Found: {info.get('found', 0)}   Valid: {info.get('valid', 0)}   Rejected: {info.get('rejected', 0)}"
            self.progress_var.set(f"{line1}\n{line2}")
            return

        if total:
            pct = 100 * scanned / total if total else 0
            if self._progress_determinate:
                self.progress_bar.configure(value=pct)
            line1 = f"Progress: {pct:5.1f}%   Scanned: {human(scanned)} / {human(total)}"
        else:
            line1 = f"Scanned: {human(scanned)}  (total size unknown for this source)"
        eta_txt = f"{int(eta)}s" if eta is not None else "—"
        line2 = f"Offset: 0x{info.get('offset', 0):X}   Speed: {human(speed)}/s   ETA: {eta_txt}"
        line3 = f"Candidates found: {info.get('found', 0)}   Valid: {info.get('valid', 0)}   Rejected: {info.get('rejected', 0)}"
        self.progress_var.set(f"{line1}\n{line2}\n{line3}")
        self._sync_results()

    def _sync_results(self):
        if self.scan is None:
            return
        results = self.scan.results
        before = self._row_count
        for idx in range(self._row_count, len(results)):
            item = results[idx]
            try:
                self.tree.insert("", "end", iid=str(idx), values=(
                    item["type"], item["extension"], f"0x{item['offset']:X}",
                    human(item["size"]), item["confidence"], item["validation"], item["status"],
                ))
            except Exception:
                # Log and skip this one row rather than let it silently abort
                # the whole sync -- previously an error here left every row
                # (not just the bad one) missing from the table with no trace.
                applog.get_logger().error(
                    "Failed to add result #%d to the table -- item=%r", idx, item, exc_info=True
                )
            finally:
                self._row_count = idx + 1  # always advance, even on failure, so we never retry-loop the same item
        if len(results) != before:
            applog.get_logger().debug(
                "Results table synced: %d -> %d rows (tree now has %d)",
                before, len(results), len(self.tree.get_children()),
            )
        validated = sum(1 for r in results if r.get("validation") == "passed")
        partial = sum(1 for r in results if r.get("validation") in ("partial", "unknown"))
        rejected = self.scan.rejected
        self.summary_var.set(
            f"Found: {len(results)}   Validated: {validated}   Partial: {partial}   Rejected: {rejected}"
        )

    def _on_scan_done(self, log):
        self._sync_results()
        applog.get_logger().info(
            "Scan finished: status=%s found=%s valid=%s rejected=%s tree_rows=%d errors=%s warnings=%s",
            log.get("status"), log.get("found"), log.get("valid"), log.get("rejected"),
            len(self.tree.get_children()), log.get("errors"), log.get("warnings"),
        )
        self.last_log = log
        self._scan_running = False  # lets Start Recovery Scan run again; self.scan itself stays set
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate", value=100 if log["status"] == "complete" else 0)
        self.pause_btn.configure(state="disabled", text="Pause")
        self.stop_btn.configure(state="disabled")
        self.start_btn.configure(state="normal")
        self.app.set_busy(False)

        status = log["status"]
        if status == "complete":
            self.status_var.set(f"Scan complete. {log['found']} candidate(s), {log['valid']} valid, "
                                 f"{log['rejected']} rejected.")
        elif status == "cancelled":
            self.status_var.set("Scan cancelled by user.")
        else:
            self.status_var.set("Scan stopped because of an error.")
            if log["errors"]:
                messagebox.showerror(APP, "The scan stopped because of an error:\n\n" + "\n".join(log["errors"]))

    def _toggle_pause(self):
        if self.scan is None:
            return
        if self._paused:
            self.scan.resume()
            self._paused = False
            self.pause_btn.configure(text="Pause")
            self.status_var.set("Resumed.")
        else:
            self.scan.pause()
            self._paused = True
            self.pause_btn.configure(text="Resume")
            self.status_var.set("Paused.")

    def _stop_scan(self):
        if self.scan is None:
            return
        self.scan.cancel()
        self.status_var.set("Stopping...")
        self.stop_btn.configure(state="disabled")

    # ------------------------------------------------------------------
    # Result actions
    # ------------------------------------------------------------------

    def _selected_indices(self):
        return [int(iid) for iid in self.tree.selection()]

    def _on_preview(self):
        indices = self._selected_indices()
        if not indices or self.scan is None:
            messagebox.showinfo(APP, "Select a result first.")
            return
        item = self.scan.results[indices[0]]
        win = tk.Toplevel(self)
        win.title(f"ByteRescue — Preview — {item['type']}")
        win.configure(bg=self.BG)
        win.geometry("640x420")
        lines = [
            f"Type: {item['type']}",
            f"Extension: {item['extension']}",
            f"Offset: 0x{item['offset']:08X}",
            f"End offset: 0x{item['end_offset']:08X}",
            f"Size: {human(item['size'])}",
        ]
        if item.get("signature"):
            lines.append(f"Signature: {item['signature']}")
        if item.get("encoding"):
            lines.append(f"Encoding: {item['encoding']}")
        lines += [
            f"Confidence: {item['confidence']}",
            f"Method: {item['method']}",
            f"Validation: {item['validation']}",
            f"Status: {item['status']}",
        ]
        text = tk.Text(win, bg="#0a0d11", fg=self.TEXT, font=("Consolas", 10), wrap="word")
        text.pack(fill="both", expand=True, padx=10, pady=10)
        text.insert("1.0", "\n".join(lines))
        if item.get("preview"):
            text.insert("end", "\n\nPreview -- possible recovery, not guaranteed to be complete:\n")
            text.insert("end", "-" * 40 + "\n" + item["preview"] + "\n" + "-" * 40)
        text.configure(state="disabled")

    def _on_recover_selected(self):
        indices = self._selected_indices()
        if not indices or self.scan is None:
            messagebox.showinfo(APP, "Select at least one result first.")
            return
        errors = []
        saved = 0
        for idx in indices:
            item = self.scan.results[idx]
            try:
                out = self.scan.write_result(item, idx + 1)
                self.tree.set(str(idx), "status", f"Saved -> {out.name}")
                saved += 1
                applog.get_logger().info("Recovered #%d (%s) -> %s", idx + 1, item.get("type"), out)
            except OSError as exc:
                errors.append(f"#{idx + 1}: {exc}")
                applog.get_logger().error("Failed to write recovered item #%d: %s", idx + 1, exc)
        self.status_var.set(f"Recovered {saved} of {len(indices)} selected item(s).")
        if errors:
            messagebox.showerror(APP, "Some items could not be written:\n\n" + "\n".join(errors))

    def _on_view_hex(self):
        indices = self._selected_indices()
        if not indices or self.scan is None:
            messagebox.showinfo(APP, "Select a result first.")
            return
        item = self.scan.results[indices[0]]
        highlight = len(item["signature"].split()) if item.get("signature") else 32
        self.app.hex_view(path=str(self.scan.source_path), focus_offset=item["offset"], highlight_length=highlight)

    def _on_export_report(self):
        if self.last_log is None or self.scan is None:
            messagebox.showinfo(APP, "Run a scan before exporting a report.")
            return
        path = filedialog.asksaveasfilename(
            title="Export recovery report", defaultextension=".json",
            filetypes=[("JSON report", "*.json")],
        )
        if not path:
            return
        try:
            export_report(self.last_log, self.scan.results, path)
            self.status_var.set(f"Report exported to {path}")
        except OSError as exc:
            messagebox.showerror(APP, f"Could not write the report.\n\n{exc}")

    def _on_open_log(self):
        log_path = applog.LOG_PATH
        if not log_path.exists():
            messagebox.showinfo(APP, "No log file yet -- nothing has been logged this session.")
            return
        try:
            os.startfile(str(log_path))
        except OSError as exc:
            messagebox.showerror(APP, f"Could not open the log file.\n\n{log_path}\n\n{exc}")

    def _on_close(self):
        if self.scan is not None and self.scan_thread_alive():
            if not messagebox.askyesno(APP, "A scan is still running. Stop it and close this window?"):
                return
            self.scan.cancel()
        self.destroy()

    def scan_thread_alive(self):
        return self.stop_btn["state"] == "normal"


def _log_thread_exception(args):
    applog.get_logger().error(
        "Unhandled exception in background thread %r:\n%s",
        args.thread.name,
        "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)),
    )


def main():
    sys.excepthook = applog.excepthook_to_log
    threading.excepthook = _log_thread_exception
    try:
        app = ByteRescue()
        app.mainloop()
    except Exception as exc:
        applog.log_exception("startup")
        # Keep startup errors visible instead of silently returning to the prompt.
        try:
            messagebox.showerror(
                APP,
                f"ByteRescue could not start.\n\n{type(exc).__name__}: {exc}\n\n"
                f"Details were written to:\n{applog.LOG_PATH}",
            )
        except Exception:
            print(f"{APP} startup error: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
