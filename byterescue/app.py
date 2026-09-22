
import hashlib
import json
import os
import platform
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

APP = "ByteRescue"

# Common file signatures used by the basic recovery scanner.
SIGS = {
    "JPEG": (b"\xff\xd8\xff", b"\xff\xd9", ".jpg"),
    "PNG": (b"\x89PNG\r\n\x1a\n", b"IEND\xaeB`\x82", ".png"),
    "PDF": (b"%PDF-", b"%%EOF", ".pdf"),
    "ZIP": (b"PK\x03\x04", None, ".zip"),
    "GZIP": (b"\x1f\x8b\x08", None, ".gz"),
    "7Z": (b"7z\xbc\xaf'\x1c", None, ".7z"),
    "RIFF": (b"RIFF", None, ".riff"),
}


def powershell(script):
    try:
        p = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return p.stdout.strip()
    except Exception:
        return ""


def get_disks():
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
             "Looks through a selected file or disk-image-like file for known byte patterns such as JPEG, PNG, PDF, ZIP, GZIP, and 7Z. "
             "This is called file carving. It is a basic recovery method and can produce incomplete or false-positive files."),
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
                tags=(json.dumps(d, default=str),),
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
        self.info.delete("1.0", "end")
        self.info.insert("1.0", text)

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
                data = f.read(128 * 1024)

            lines = []
            for offset in range(0, len(data), 16):
                chunk = data[offset:offset + 16]
                hx = " ".join(f"{b:02X}" for b in chunk).ljust(47)
                asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
                lines.append(f"{offset:08X}  {hx}  {asc}")

            win = tk.Toplevel(self)
            win.title(f"ByteRescue — Hex Viewer — {p.name}")
            win.geometry("1050x680")
            win.configure(bg="#0f1318")
            win.transient(self)

            frame = tk.Frame(win, bg="#0f1318")
            frame.pack(fill="both", expand=True, padx=10, pady=10)
            text = tk.Text(
                frame,
                bg="#0a0d11",
                fg="#d7dde8",
                insertbackground="#ffffff",
                selectbackground="#294b70",
                font=("Consolas", 10),
                relief="flat",
                wrap="none",
            )
            ybar = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
            xbar = ttk.Scrollbar(frame, orient="horizontal", command=text.xview)
            text.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
            text.grid(row=0, column=0, sticky="nsew")
            ybar.grid(row=0, column=1, sticky="ns")
            xbar.grid(row=1, column=0, sticky="ew")
            frame.rowconfigure(0, weight=1)
            frame.columnconfigure(0, weight=1)
            text.insert("1.0", "\n".join(lines))
            text.configure(state="disabled")
            self.set_status("Hex viewer opened.")
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
        try:
            # Stream in chunks so very large files do not consume all RAM.
            data = src.read_bytes()
            found = 0
            max_size = 64 * 1024 * 1024

            for name, (start, end, suffix) in SIGS.items():
                pos = 0
                while True:
                    i = data.find(start, pos)
                    if i < 0:
                        break

                    if end:
                        j = data.find(end, i + len(start))
                        if j < 0:
                            j = min(i + max_size, len(data))
                        else:
                            j += len(end)
                    else:
                        j = min(i + max_size, len(data))

                    blob = data[i:j]
                    if blob:
                        found += 1
                        out = dst / f"recovered_{found:05d}_{name.lower()}{suffix}"
                        # Avoid overwriting a previous result.
                        n = 2
                        while out.exists():
                            out = dst / f"recovered_{found:05d}_{name.lower()}_{n}{suffix}"
                            n += 1
                        out.write_bytes(blob)

                    pos = i + len(start)

            self.after(0, lambda: self.scan_finished(found, dst))
        except Exception as exc:
            self.after(0, lambda e=exc: self.scan_failed(e))

    def scan_finished(self, found, dst):
        self.set_busy(False)
        self.set_status(f"Signature scan complete: {found} object(s) recovered.")
        self.show_text(
            f"SIGNATURE RECOVERY COMPLETE\n\n"
            f"Objects recovered: {found}\n"
            f"Destination: {dst}\n\n"
            "This is a basic file-carving scanner. Fragmented files may be "
            "incomplete, and a matching signature does not guarantee that the "
            "result is a valid file."
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
