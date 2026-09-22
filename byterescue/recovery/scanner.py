"""Scan orchestration: reads a source (read-only), finds candidates via
signatures.py / text_recovery.py, and writes accepted ones to a destination.

Two source strategies, used for different reasons:

  - mmap (`_scan_mmap`): used for an ordinary file or disk-image FILE. The
    whole file is one addressable range, so there is no chunk-boundary
    problem to solve at all -- simplest and fastest option when it's
    available.
  - ChunkedReader (`_scan_chunked`): used for "Deep / Raw Scan" mode, which
    is meant to also work against a raw physical-drive path. Windows
    device paths generally don't report a usable size via stat(), so mmap
    isn't reliable there; this reads fixed-size chunks with an overlap
    buffer instead, so a signature split across a chunk boundary is still
    complete within at least one window. A format whose true end lies
    beyond the current window (rare -- a huge embedded video/archive) is
    reported as boundary-truncated instead of silently guessed at.
"""

import hashlib
import json
import mmap
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from . import filesystem
from . import signatures
from . import text_recovery

FS_MAX_RECOVERED_SIZE = 2 * 1024 * 1024 * 1024  # sanity ceiling against a corrupt/garbage size field

DEFAULT_CHUNK_SIZE = 8 * 1024 * 1024
DEFAULT_OVERLAP = 1 * 1024 * 1024   # comfortably longer than any signature/footer used
PROGRESS_INTERVAL_SECONDS = 0.5


def sha256_bytes(blob):
    return hashlib.sha256(blob).hexdigest()


def is_device_path(path):
    """True for a raw Win32 device-namespace path (\\\\.\\PhysicalDriveN or
    \\\\?\\...). These must NEVER be passed through pathlib.Path(): pathlib
    parses '\\\\.\\PhysicalDrive2' as a UNC path (server '.', share
    'PhysicalDrive2') and str()'s it back out as '\\\\.\\PhysicalDrive2\\'
    -- WITH a trailing backslash, which Windows then refuses to open
    (raises PermissionError, not a helpful "bad path" error). Keep a device
    path a plain str all the way to open()/os.stat() and this never happens.
    """
    s = str(path).upper()
    return s.startswith("\\\\.\\") or s.startswith("\\\\?\\")


def destination_is_risky(source_path, destination_dir):
    """True if writing recovered files to destination_dir could overwrite
    the very data being recovered: same path, same parent folder, or (when
    the source is a drive path like \\\\.\\PhysicalDrive0) the same drive
    letter as the destination. Callers should warn, not silently block --
    the user may have a good reason (e.g. recovering to a different
    partition on purpose)."""
    if is_device_path(source_path):
        # Can't resolve a parent folder for a device path -- just flag it
        # for confirmation; the GUI is responsible for the actual wording.
        return True

    try:
        src = Path(source_path).resolve()
    except OSError:
        src = Path(source_path)
    try:
        dst = Path(destination_dir).resolve()
    except OSError:
        dst = Path(destination_dir)

    if dst == src or dst == src.parent:
        return True
    try:
        dst.relative_to(src if src.is_dir() else src.parent)
        return True
    except ValueError:
        return False


def _guess_extension(name):
    dot = name.rfind(".")
    if 0 < dot < len(name) - 1:
        ext = name[dot:].lower()
        if len(ext) <= 8 and ext[1:].isalnum():
            return ext
    return ".bin"


_WINDOWS_UNSAFE_NAME_CHARS = '<>:"/\\|?*'


def safe_output_path(dst, index, type_name, ext, tag="", original_name=None):
    """Never overwrite an existing recovered file. `original_name` is used
    when a caller actually has one -- e.g. filesystem-mode recovery, which
    reads it straight from a FAT directory entry -- sanitized against
    characters Windows filenames can't contain (the FAT/VFAT character set
    allows a few of these that NTFS-mounted Windows would still reject)."""
    if original_name:
        cleaned = "".join(c if c not in _WINDOWS_UNSAFE_NAME_CHARS else "_" for c in original_name)
        stem = Path(cleaned).stem[:80].strip() or "recovered"
        base = f"{stem}{tag}{ext}"
    else:
        base = f"recovered_{index:06d}_{type_name.lower()}{tag}{ext}"
    out = dst / base
    n = 2
    while out.exists():
        if original_name:
            out = dst / f"{Path(base).stem}_{n}{ext}"
        else:
            out = dst / f"recovered_{index:06d}_{type_name.lower()}{tag}_{n}{ext}"
        n += 1
    return out


class ChunkedReader:
    """Sequential chunked reader with an overlap window carried between reads."""

    def __init__(self, path, chunk_size=DEFAULT_CHUNK_SIZE, overlap=DEFAULT_OVERLAP):
        self.path = path
        self.chunk_size = chunk_size
        self.overlap = overlap

    def __iter__(self):
        with open(self.path, "rb") as f:
            file_pos = 0
            carry = b""
            while True:
                chunk = f.read(self.chunk_size)
                if not chunk:
                    break
                window_start = file_pos - len(carry)
                buf = carry + chunk
                yield window_start, buf
                file_pos += len(chunk)
                carry = buf[-self.overlap:] if len(buf) > self.overlap else buf


class ScanCancelled(Exception):
    pass


class RecoveryScan:
    """Owns one recovery run: source, destination, selected formats/mode,
    pause/resume/cancel, progress, dedup, the recovered-items list, and the
    session log. Call run() from a background thread; it blocks until done,
    paused, or cancelled, calling `progress_cb` periodically."""

    def __init__(self, source_path, destination_dir, mode="signature",
                 selected_formats=None, use_chunked=False,
                 chunk_size=DEFAULT_CHUNK_SIZE, overlap=DEFAULT_OVERLAP,
                 min_text_length=text_recovery.DEFAULT_MIN_LENGTH,
                 progress_cb=None, source_label=None):
        # Device paths (\\.\PhysicalDriveN) MUST stay a plain str -- see is_device_path().
        self.source_path = str(source_path) if is_device_path(source_path) else Path(source_path)
        self.destination_dir = Path(destination_dir)
        if mode not in ("signature", "text", "filesystem"):
            raise ValueError(f"unknown scan mode {mode!r} -- must be 'signature', 'text', or 'filesystem'")
        self.mode = mode
        # "Deep / Raw Scan" in the GUI is NOT a fourth mode here -- it is
        # mode="signature" with use_chunked=True. Chunking is an orthogonal
        # reading strategy (see module docstring), not a different search.
        # mode="filesystem" (FAT12/16/32 only -- see recovery.filesystem)
        # ignores use_chunked entirely: it needs random seek access to the
        # boot sector/FAT/directory clusters, which ChunkedReader's
        # sequential-with-overlap model doesn't provide, and doesn't need
        # mmap's up-front size either. See _scan_filesystem().
        self.selected_formats = selected_formats or list(signatures.SIGNATURES)
        self.use_chunked = use_chunked
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.min_text_length = min_text_length
        self.progress_cb = progress_cb or (lambda info: None)
        self.source_label = source_label or str(source_path)

        self._pause_event = threading.Event()
        self._pause_event.set()  # set = not paused
        self._cancel_event = threading.Event()

        self.results = []
        self.warnings = []
        self.errors = []
        self._seen = set()  # (name, start_offset) dedup key
        self._found = 0
        self._valid = 0
        self._rejected = 0
        self._bytes_scanned = 0
        self._total_bytes = None
        self._start_time = None

    def pause(self):
        self._pause_event.clear()

    def resume(self):
        self._pause_event.set()

    def cancel(self):
        self._cancel_event.set()
        self._pause_event.set()  # unblock a paused wait so it can see the cancel

    def _checkpoint(self):
        self._pause_event.wait()
        if self._cancel_event.is_set():
            raise ScanCancelled()

    def _emit_progress(self, offset):
        now = time.monotonic()
        if now - self._last_progress_at < PROGRESS_INTERVAL_SECONDS:
            return
        self._last_progress_at = now
        elapsed = max(1e-6, now - self._start_time)
        speed = self._bytes_scanned / elapsed
        eta = None
        if self._total_bytes:
            remaining = max(0, self._total_bytes - self._bytes_scanned)
            eta = remaining / speed if speed > 0 else None
        self.progress_cb({
            "offset": offset, "bytes_scanned": self._bytes_scanned,
            "total_bytes": self._total_bytes, "speed_bytes_s": speed, "eta_seconds": eta,
            "found": self._found, "valid": self._valid, "rejected": self._rejected,
            # filesystem mode counts directory entries walked, not bytes swept --
            # callers must not format it with a byte-size unit.
            "unit": "entries" if self.mode == "filesystem" else "bytes",
        })

    @property
    def found(self):
        return self._found

    @property
    def valid(self):
        return self._valid

    @property
    def rejected(self):
        return self._rejected

    def run(self):
        self._start_time = time.monotonic()
        self._last_progress_at = 0.0
        self._started_at = datetime.now(timezone.utc).isoformat()
        if self.mode == "filesystem" or is_device_path(self.source_path):
            # stat() on a raw device path "succeeds" but always reports
            # st_size=0 -- it does NOT report the drive's real capacity.
            # Trusting that 0 would hit the "empty source, nothing to do"
            # short-circuit below and silently "complete" a scan that never
            # read a single byte. filesystem mode never needs a total size
            # up front either (see _scan_filesystem), so skip stat() there too.
            self._total_bytes = None
        else:
            try:
                self._total_bytes = os.stat(self.source_path).st_size
            except OSError:
                self._total_bytes = None

        try:
            if self.mode == "filesystem":
                self._scan_filesystem()
            elif self._total_bytes == 0:
                pass
            elif self.use_chunked or self._total_bytes is None:
                self._scan_chunked()
            else:
                self._scan_mmap()
            status = "cancelled" if self._cancel_event.is_set() else "complete"
        except ScanCancelled:
            status = "cancelled"
        except PermissionError as exc:
            msg = f"Access denied: {exc}"
            if is_device_path(self.source_path):
                msg += (
                    ". Raw physical-drive access needs ByteRescue itself to be elevated (right-click "
                    "ByteRescue.bat -> Run as administrator -- launching a non-elevated shortcut that then "
                    "opens an elevated one doesn't count), and Windows can still refuse it if the drive has "
                    "a mounted volume that another process (Explorer, antivirus, a backup tool) has open, or "
                    "if the removable media itself is write/read-protected. If it still fails, image the "
                    "drive to a .img/.dd file with dedicated imaging software first and scan that file "
                    "instead -- Recover by Signature/Text on a file source does not need raw device access."
                )
            self.errors.append(msg)
            status = "error"
        except FileNotFoundError as exc:
            self.errors.append(f"Source disappeared during scan: {exc}")
            status = "error"
        except OSError as exc:
            self.errors.append(f"Read error: {exc}")
            status = "error"

        self.progress_cb({
            "offset": self._bytes_scanned, "bytes_scanned": self._bytes_scanned,
            "total_bytes": self._total_bytes, "speed_bytes_s": 0, "eta_seconds": 0,
            "found": self._found, "valid": self._valid, "rejected": self._rejected,
            "unit": "entries" if self.mode == "filesystem" else "bytes",
            "done": True, "status": status,
        })
        self._finished_at = datetime.now(timezone.utc).isoformat()
        return self._build_log(status)

    # -- source strategies ---------------------------------------------------

    def _scan_mmap(self):
        with open(self.source_path, "rb") as f, \
                mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as data:
            if self.mode == "signature":
                self._scan_signatures_in(data, 0)
            elif self.mode == "text":
                self._scan_text_in(data, 0)
            self._bytes_scanned = len(data)
            self._emit_progress(len(data))

    def _scan_chunked(self):
        reader = ChunkedReader(self.source_path, self.chunk_size, self.overlap)
        for window_start, buf in reader:
            self._checkpoint()
            if self.mode == "signature":
                self._scan_signatures_in(buf, window_start, window_end_exclusive=True)
            elif self.mode == "text":
                self._scan_text_in(buf, window_start)
            self._bytes_scanned = window_start + len(buf)
            self._emit_progress(self._bytes_scanned)

    def _scan_filesystem(self):
        # FAT12/16/32 only -- see recovery.filesystem for exactly what this
        # can and can't recover, especially the "assumes contiguous
        # allocation for deleted files" limitation.
        with filesystem.RandomAccessSource(self.source_path) as reader:
            bpb = filesystem.probe(reader)
            if bpb is None:
                self.errors.append(
                    "Not a recognizable FAT12/16/32 volume (or this is NTFS/exFAT, which "
                    "filesystem-aware recovery does not support yet). No filesystem-level "
                    "recovery was attempted; try Recover by Signature or Recover Text Files instead."
                )
                return

            entries = filesystem.walk(reader, bpb)
            for entry in entries:
                self._checkpoint()
                if entry["is_dir"] or not entry["deleted"]:
                    continue  # only deleted FILES are recovery candidates here
                self._found += 1

                key = ("FAT-DELETED", entry["path"])
                if key in self._seen:
                    continue
                self._seen.add(key)

                if entry["size"] == 0 or entry["size"] > FS_MAX_RECOVERED_SIZE:
                    self._rejected += 1  # zero-size or implausibly large -- corrupt entry, not a real candidate
                    continue

                try:
                    data, chain_verified = filesystem.read_entry_bytes(reader, bpb, entry)
                except Exception as exc:
                    self._rejected += 1
                    self.warnings.append(f"Could not read {entry['path']!r}: {exc}")
                    continue
                if not data:
                    self._rejected += 1
                    continue

                n_clusters = (entry["size"] + bpb["cluster_bytes"] - 1) // bpb["cluster_bytes"]
                offset = filesystem._cluster_offset(bpb, entry["first_cluster"])
                ext = _guess_extension(entry["name"])

                guessed_format = signatures.guess_format(data)
                validation = "unknown"
                if guessed_format:
                    validation = signatures.validate(guessed_format, data, chain_verified)

                if n_clusters <= 1:
                    confidence = "High"  # single cluster -- no chain assumption needed at all
                    status = f"Recovered deleted FAT entry '{entry['name']}' (fits in one cluster)"
                else:
                    confidence = "Low"
                    status = (
                        f"Recovered deleted FAT entry '{entry['name']}' -- ASSUMED CONTIGUOUS across "
                        f"{n_clusters} clusters (the real cluster chain is gone; if this file was "
                        f"fragmented on disk, only the first cluster's worth of data is correct)"
                    )

                self._valid += 1
                self.results.append({
                    "kind": "filesystem", "type": "FAT-DELETED", "extension": ext,
                    "offset": offset, "end_offset": offset + len(data), "size": len(data),
                    "signature": None, "confidence": confidence, "method": "filesystem (FAT directory entry)",
                    "validation": validation, "status": status, "verified": False,
                    "sha256": None, "blob": data, "original_name": entry["name"],
                    "encoding": None, "preview": None,
                })
            self._bytes_scanned = len(entries)
            self._emit_progress(self._bytes_scanned)

    # -- signature scanning ---------------------------------------------------

    def _scan_signatures_in(self, data, base_offset, window_end_exclusive=False):
        window_len = len(data)
        for name in self.selected_formats:
            if name not in signatures.SIGNATURES:
                continue
            spec = signatures.SIGNATURES[name]
            header = spec["header"]
            pos = 0
            while True:
                self._checkpoint()
                found = signatures.find_header_match(data, header, pos)
                if found is None:
                    break
                local_i, matched_header = found
                abs_offset = base_offset + local_i

                if (name, abs_offset) in self._seen:
                    pos = local_i + 1
                    continue

                self._found += 1
                result = signatures.carve(name, data, local_i)
                if result is None:
                    self._rejected += 1
                    pos = local_i + 1
                    continue

                end = result["end"]
                hit_window_edge = window_end_exclusive and end >= window_len and not result["verified"]
                blob_len = end - local_i
                if blob_len < spec["min_size"]:
                    self._rejected += 1
                    pos = local_i + len(matched_header)
                    continue

                blob = bytes(data[local_i:end])
                self._seen.add((name, abs_offset))
                self._record_signature_hit(name, abs_offset, blob, result, matched_header, hit_window_edge)
                self._valid += 1

                pos = end if result["verified"] else local_i + len(matched_header)

    def _record_signature_hit(self, name, abs_offset, blob, result, matched_header, hit_window_edge):
        ext = result["ext"]
        verified = result["verified"] and not hit_window_edge
        if name == "ZIP" and verified:
            ooxml_ext = signatures.detect_ooxml_extension(blob)
            if ooxml_ext:
                ext = ooxml_ext
        validation = signatures.validate(name, blob, verified)
        status = signatures.fragmentation_status(verified, validation, hit_cap=not verified)
        if hit_window_edge:
            status = "Unknown (extends past this scan window)"

        item = {
            "kind": "signature", "type": name, "extension": ext,
            "offset": abs_offset, "end_offset": abs_offset + len(blob), "size": len(blob),
            "signature": " ".join(f"{b:02X}" for b in matched_header),
            "confidence": "High" if verified else "Low",
            "method": "signature", "validation": validation, "status": status,
            "verified": verified, "sha256": None, "blob": blob,
        }
        self.results.append(item)

    # -- text scanning ---------------------------------------------------

    def _scan_text_in(self, data, base_offset):
        buf = bytes(data) if not isinstance(data, (bytes, bytearray)) else data
        for cand in text_recovery.find_candidates(buf, base_offset, self.min_text_length):
            self._checkpoint()
            key = ("TEXT", cand["offset"])
            self._found += 1
            if key in self._seen:
                continue
            self._seen.add(key)
            self._valid += 1
            self.results.append({
                "kind": "text", "type": "TEXT", "extension": ".txt",
                "offset": cand["offset"], "end_offset": cand["offset"] + cand["length"],
                "size": cand["length"], "signature": None,
                "confidence": f"{cand['confidence'] * 100:.0f}%",
                "method": "text-pattern", "validation": "unknown",
                "status": "Possible recovery -- not guaranteed to be complete",
                "verified": False, "sha256": None,
                "encoding": cand["encoding"], "preview": text_recovery.preview_text(cand),
                "preview_raw": cand["preview_raw"],
            })

    # -- writing results ---------------------------------------------------

    def write_result(self, item, index):
        """Materialize one result to destination_dir. For signature hits the
        full blob was already read during scanning; for text hits (which can
        legitimately be huge) this re-reads just that byte range from the
        source instead of keeping every candidate's full bytes in memory."""
        self.destination_dir.mkdir(parents=True, exist_ok=True)
        tag = "" if item["verified"] else "_unverified"
        out = safe_output_path(self.destination_dir, index, item["type"], item["extension"], tag,
                                original_name=item.get("original_name"))

        if item["kind"] in ("signature", "filesystem"):
            blob = item["blob"]
        else:
            with open(self.source_path, "rb") as f:
                f.seek(item["offset"])
                blob = f.read(item["size"])

        out.write_bytes(blob)
        item["sha256"] = sha256_bytes(blob)
        item["saved_to"] = str(out)
        return out

    # -- session log ---------------------------------------------------

    def _build_log(self, status):
        return {
            "started_at": getattr(self, "_started_at", None),
            "finished_at": getattr(self, "_finished_at", None),
            "source": self.source_label,
            "mode": self.mode,
            "formats_selected": list(self.selected_formats) if self.mode == "signature" else None,
            "destination": str(self.destination_dir),
            "status": status,
            "bytes_scanned": self._bytes_scanned,
            "total_bytes": self._total_bytes,
            "found": self._found,
            "valid": self._valid,
            "rejected": self._rejected,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }


def export_report(log, results, path):
    """Write a JSON recovery report. Only metadata is recorded (offsets,
    sizes, hashes, validation) -- not recovered file contents."""
    report = dict(log)
    report["items"] = [
        {k: v for k, v in item.items() if k not in ("blob", "preview_raw")}
        for item in results
    ]
    Path(path).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
