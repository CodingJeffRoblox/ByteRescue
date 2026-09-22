"""Signature-based carving: what SIGNATURES the scanner knows, and the real
logic that finds where each recovered object actually ends.

Every SIGNATURES entry needs matching carve logic below -- nothing is
listed "for show". Two families of formats, handled differently:

  - Weak/short magics (ZIP, RIFF, SQLite, BMP, PE, ELF, MP4) get a real
    structural check. If that check fails, the candidate is REJECTED
    outright (not emitted at all) -- a failed structural check on a weak
    magic is good evidence it was a coincidental byte match, not a damaged
    real file.
  - Strong/long magics (JPEG, PNG, PDF, GZIP, 7Z, FLAC, GIF, TIFF, RAR,
    OLE, MKV, ID3) are accepted even without a confirmed end, since the
    magic itself is distinctive enough to be worth keeping -- but they are
    tagged unverified/capped rather than claimed complete.
"""

import struct

JPEG_MAX_BYTES = 64 * 1024 * 1024          # JPEGs essentially never exceed this
PDF_MAX_BYTES = 256 * 1024 * 1024
UNVERIFIED_CAP_BYTES = 512 * 1024 * 1024   # generic cap for "no reliable footer" formats

# name -> metadata. "carver" selects the dispatch branch in carve() below.
SIGNATURES = {
    "JPEG": {
        "extensions": [".jpg", ".jpeg"], "header": b"\xff\xd8\xff", "footer": b"\xff\xd9",
        "carver": "jpeg", "min_size": 20, "max_size": JPEG_MAX_BYTES,
        "reliable": True, "container_based": False, "false_positive_risk": "low",
        "notes": "Footer search uses the LAST End-of-Image before the next header, "
                 "since embedded EXIF thumbnails have their own earlier EOI.",
    },
    "PNG": {
        "extensions": [".png"], "header": b"\x89PNG\r\n\x1a\n", "footer": b"IEND\xaeB`\x82",
        "carver": "png", "min_size": 45, "max_size": None,
        "reliable": True, "container_based": True, "false_positive_risk": "very low",
        "notes": "IEND always has zero-length chunk data, so its CRC is a fixed constant -- "
                 "an 8-byte footer that is effectively unforgeable by coincidence.",
    },
    "PDF": {
        "extensions": [".pdf"], "header": b"%PDF-", "footer": b"%%EOF",
        "carver": "pdf", "min_size": 20, "max_size": PDF_MAX_BYTES,
        "reliable": True, "container_based": False, "false_positive_risk": "low",
        "notes": "A PDF can have multiple %%EOF markers (incremental saves) -- "
                 "the last one before the next %PDF- is used.",
    },
    "ZIP": {
        "extensions": [".zip"], "header": b"PK\x03\x04", "footer": b"PK\x05\x06",
        "carver": "zip", "min_size": 22, "max_size": None,
        "reliable": True, "container_based": True, "false_positive_risk": "low",
        "notes": "A ZIP can contain many Local File Headers (one per entry). Only the "
                 "End Of Central Directory record marks the real end of the archive; "
                 "entries without one are rejected, not guessed at.",
    },
    "GZIP": {
        "extensions": [".gz"], "header": b"\x1f\x8b\x08", "footer": None,
        "carver": "capped", "min_size": 18, "max_size": UNVERIFIED_CAP_BYTES,
        "reliable": False, "container_based": False, "false_positive_risk": "low",
        "notes": "No footer magic exists for GZIP; end is a capped guess.",
    },
    "7Z": {
        "extensions": [".7z"], "header": b"7z\xbc\xaf'\x1c", "footer": None,
        "carver": "capped", "min_size": 32, "max_size": UNVERIFIED_CAP_BYTES,
        "reliable": False, "container_based": True, "false_positive_risk": "very low",
        "notes": "No simple footer magic; end header is a checksummed structure with no "
                 "fixed byte pattern to search for.",
    },
    "FLAC": {
        "extensions": [".flac"], "header": b"fLaC", "footer": None,
        "carver": "capped", "min_size": 42, "max_size": UNVERIFIED_CAP_BYTES,
        "reliable": False, "container_based": False, "false_positive_risk": "low",
        "notes": "No footer magic; end is a capped guess.",
    },
    "RIFF": {
        "extensions": [".riff", ".wav", ".avi", ".webp"], "header": b"RIFF", "footer": None,
        "carver": "riff", "min_size": 12, "max_size": None,
        "reliable": True, "container_based": True, "false_positive_risk": "low",
        "notes": "RIFF stores its own total length right after the 'RIFF' tag, so the "
                 "real end is computed, not guessed. Extension (.wav/.avi/.webp) comes "
                 "from the format tag at offset 8; unrecognized tags are rejected.",
    },
    "SQLITE": {
        "extensions": [".sqlite", ".db"], "header": b"SQLite format 3\x00", "footer": None,
        "carver": "sqlite", "min_size": 512, "max_size": None,
        "reliable": True, "container_based": False, "false_positive_risk": "very low",
        "notes": "Header stores page size and page count; their product is the exact "
                 "documented file size.",
    },
    "BMP": {
        "extensions": [".bmp"], "header": b"BM", "footer": None,
        "carver": "bmp", "min_size": 54, "max_size": None,
        "reliable": True, "container_based": False, "false_positive_risk": "high (2-byte magic)",
        "notes": "'BM' alone is far too common to trust -- only accepted when the embedded "
                 "file-size field AND a known DIB-header-size value both look plausible.",
    },
    "GIF": {
        "extensions": [".gif"], "header": (b"GIF87a", b"GIF89a"), "footer": b"\x3b",
        "carver": "capped", "min_size": 20, "max_size": UNVERIFIED_CAP_BYTES,
        "reliable": False, "container_based": True, "false_positive_risk": "low (header)",
        "notes": "Trailer byte (0x3B) is too common to search for on its own, so it is "
                 "NOT used as a footer here; end is a capped guess instead.",
    },
    "TIFF": {
        "extensions": [".tif", ".tiff"], "header": (b"II*\x00", b"MM\x00*"), "footer": None,
        "carver": "capped", "min_size": 16, "max_size": UNVERIFIED_CAP_BYTES,
        "reliable": False, "container_based": True, "false_positive_risk": "low",
        "notes": "No simple end marker; IFDs are scattered through the file. Full IFD "
                 "walking is not implemented, so end is a capped guess.",
    },
    "RAR": {
        "extensions": [".rar"], "header": (b"Rar!\x1a\x07\x00", b"Rar!\x1a\x07\x01\x00"), "footer": None,
        "carver": "capped", "min_size": 20, "max_size": UNVERIFIED_CAP_BYTES,
        "reliable": False, "container_based": True, "false_positive_risk": "very low",
        "notes": "Proprietary block structure with no simple footer; end is a capped guess.",
    },
    "OLE": {
        "extensions": [".doc", ".xls", ".ppt"], "header": b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "footer": None,
        "carver": "capped", "min_size": 512, "max_size": UNVERIFIED_CAP_BYTES,
        "reliable": False, "container_based": True, "false_positive_risk": "very low",
        "notes": "Legacy Office compound-file format (pre-2007). Real end requires walking "
                 "its internal sector allocation table, which is not implemented; capped guess. "
                 "Extension defaults to .doc -- the real type cannot be told from the header alone.",
    },
    "MKV": {
        "extensions": [".mkv", ".webm"], "header": b"\x1a\x45\xdf\xa3", "footer": None,
        "carver": "capped", "min_size": 64, "max_size": UNVERIFIED_CAP_BYTES,
        "reliable": False, "container_based": True, "false_positive_risk": "very low",
        "notes": "EBML/Matroska structure; some files even declare an 'unknown' segment "
                 "size (common for recordings). Full EBML walking is not implemented.",
    },
    "MP3_ID3": {
        "extensions": [".mp3"], "header": b"ID3", "footer": None,
        "carver": "capped", "min_size": 10, "max_size": UNVERIFIED_CAP_BYTES,
        "reliable": False, "container_based": False, "false_positive_risk": "medium",
        "notes": "Detects an ID3v2 TAG, not audio frames. Raw MPEG frame-sync bytes are "
                 "deliberately NOT used as a signature -- they recur constantly inside "
                 "valid compressed audio and would false-positive relentlessly. Many real "
                 "MP3s have no ID3v2 tag at all and are not detected by this entry.",
    },
    "PE": {
        "extensions": [".exe", ".dll"], "header": b"MZ", "footer": None,
        "carver": "pe", "min_size": 64, "max_size": None,
        "reliable": True, "container_based": True, "false_positive_risk": "high (2-byte magic)",
        "notes": "'MZ' alone is far too common. Only accepted when the DOS-header pointer "
                 "leads to a valid 'PE\\0\\0' header with a sane section table; end is "
                 "computed from the section table (and the security/signature directory "
                 "when present), not guessed.",
    },
    "ELF": {
        "extensions": [".elf", ".so", ".bin"], "header": b"\x7fELF", "footer": None,
        "carver": "elf", "min_size": 52, "max_size": None,
        "reliable": True, "container_based": True, "false_positive_risk": "low",
        "notes": "End computed from the section header table (e_shoff/e_shnum/e_shentsize). "
                 "Stripped binaries with no section headers are rejected, not guessed at.",
    },
    "MP4": {
        "extensions": [".mp4", ".mov", ".m4a", ".3gp"], "header": b"ftyp", "footer": None,
        "carver": "mp4", "min_size": 32, "max_size": None,
        "reliable": True, "container_based": True, "false_positive_risk": "low",
        "notes": "ISO-BMFF box format. End is computed by walking sibling top-level boxes "
                 "from the ftyp box, honoring the 64-bit largesize extension and the "
                 "size==0 ('extends to EOF') case, instead of guessing.",
    },
}


def find_header_match(data, headers, pos):
    """headers may be a single bytes or a tuple of alternates; return (index, matched_bytes)."""
    if isinstance(headers, bytes):
        headers = (headers,)
    best = None
    for h in headers:
        j = data.find(h, pos)
        if j >= 0 and (best is None or j < best[0]):
            best = (j, h)
    return best


def _carve_footer_last(data, start_i, header_len, footer, cap):
    # LAST footer within the cap (not the first) -- avoids truncating at a
    # JPEG's embedded EXIF thumbnail EOI or an earlier PDF %%EOF revision.
    # Deliberately NOT bounded by "the next header of this format": a
    # thumbnail's own SOI is indistinguishable from a genuinely separate
    # next file's SOI by byte pattern alone, and bounding on it reintroduces
    # the exact truncation bug this function exists to avoid. The trade-off
    # is that two same-format files placed back-to-back with zero bytes of
    # gap between them could get merged into one recovered blob; validate()
    # is the backstop that catches format-level damage from a wrong guess.
    bound = min(len(data), start_i + cap)
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
    return (last + len(footer), True)  # a real footer was located


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


def detect_ooxml_extension(blob):
    """Peek inside an already-carved, valid ZIP to see if it's really an
    Office Open XML document -- DOCX/XLSX/PPTX are ZIPs with a telltale
    internal entry, not a distinct file format with its own magic bytes."""
    import io
    import zipfile
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            names = set(z.namelist())
    except Exception:
        return None
    if "word/document.xml" in names:
        return ".docx"
    if "xl/workbook.xml" in names:
        return ".xlsx"
    if "ppt/presentation.xml" in names:
        return ".pptx"
    return None


def _carve_riff(data, i):
    # RIFF stores its own length (4 bytes right after "RIFF"), so the real end
    # is computable, not guessed. Offset-8 tag also gives the real extension.
    if i + 12 > len(data):
        return None
    (size,) = struct.unpack_from("<I", data, i + 4)
    fourcc = data[i + 8:i + 12]
    ext = {b"WAVE": ".wav", b"AVI ": ".avi", b"WEBP": ".webp"}.get(fourcc)
    if ext is None:
        return None  # unrecognized RIFF subtype -- reject rather than guess
    end = i + 8 + size
    if size < 4 or end > len(data):
        return None
    return (end, ext, True)


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


def _carve_bmp(data, i):
    # "BM" alone is a 2-byte magic (very common) -- require the embedded file
    # size AND a recognized DIB header size before trusting the match at all.
    if i + 26 > len(data):
        return None
    (file_size,) = struct.unpack_from("<I", data, i + 2)
    (dib_size,) = struct.unpack_from("<I", data, i + 14)
    if dib_size not in (12, 40, 52, 56, 64, 108, 124):
        return None
    end = i + file_size
    if file_size < 54 or end > len(data):
        return None
    return (end, True)


def _carve_pe(data, i):
    # "MZ" alone is a 2-byte magic -- only trust it once the DOS header's
    # e_lfanew pointer leads to a real "PE\0\0" header with a sane section
    # table. End = furthest (PointerToRawData + SizeOfRawData) across
    # sections, extended to cover an appended Authenticode signature block
    # (the security directory) when present.
    if i + 0x40 > len(data):
        return None
    (e_lfanew,) = struct.unpack_from("<I", data, i + 0x3C)
    pe_off = i + e_lfanew
    if pe_off < i or pe_off + 24 > len(data):
        return None
    if data[pe_off:pe_off + 4] != b"PE\x00\x00":
        return None

    file_header = pe_off + 4
    (num_sections,) = struct.unpack_from("<H", data, file_header + 2)
    (opt_size,) = struct.unpack_from("<H", data, file_header + 16)
    opt_header_off = file_header + 20
    section_table_off = opt_header_off + opt_size

    if not (0 < num_sections <= 96):
        return None
    if section_table_off + num_sections * 40 > len(data):
        return None

    end = section_table_off + num_sections * 40
    for s in range(num_sections):
        base = section_table_off + s * 40
        size_of_raw, ptr_raw = struct.unpack_from("<II", data, base + 16)
        if ptr_raw or size_of_raw:
            end = max(end, ptr_raw + size_of_raw)

    if opt_size >= 2:
        (magic,) = struct.unpack_from("<H", data, opt_header_off)
        dir_base = None
        if magic == 0x10B:      # PE32
            dir_base = opt_header_off + 96
        elif magic == 0x20B:    # PE32+
            dir_base = opt_header_off + 112
        if dir_base is not None and dir_base + 8 * 5 <= len(data):
            # Directory index 4 = IMAGE_DIRECTORY_ENTRY_SECURITY. Its
            # "VirtualAddress" is, unusually, a raw file offset (not an RVA).
            sec_off, sec_size = struct.unpack_from("<II", data, dir_base + 4 * 8)
            if sec_size:
                end = max(end, sec_off + sec_size)

    end = min(end, len(data))
    if end <= i:
        return None
    return (end, True)


def _carve_elf(data, i):
    # End computed from the section header table -- e_shoff + e_shnum*e_shentsize.
    # Stripped binaries (no section headers) can't be measured this way; reject.
    if i + 20 > len(data):
        return None
    ei_class, ei_data = data[i + 4], data[i + 5]
    if ei_class not in (1, 2) or ei_data not in (1, 2):
        return None
    endian = "<" if ei_data == 1 else ">"

    if ei_class == 1:  # ELF32
        if i + 52 > len(data):
            return None
        (e_shoff,) = struct.unpack_from(endian + "I", data, i + 32)
        (e_shentsize,) = struct.unpack_from(endian + "H", data, i + 46)
        (e_shnum,) = struct.unpack_from(endian + "H", data, i + 48)
    else:  # ELF64
        if i + 64 > len(data):
            return None
        (e_shoff,) = struct.unpack_from(endian + "Q", data, i + 40)
        (e_shentsize,) = struct.unpack_from(endian + "H", data, i + 58)
        (e_shnum,) = struct.unpack_from(endian + "H", data, i + 60)

    if e_shoff == 0 or e_shnum == 0:
        return None
    end = i + e_shoff + e_shentsize * e_shnum
    if end <= i or end > len(data):
        return None
    return (end, True)


def _carve_mp4(data, ftyp_idx):
    # ISO-BMFF: walk sibling top-level boxes (4-byte size + 4-byte type,
    # or a 64-bit "largesize" when size==1) from the ftyp box until a
    # size==0 box ("extends to EOF") or the data runs out.
    box_start = ftyp_idx - 4
    if box_start < 0 or box_start + 8 > len(data):
        return None
    (size,) = struct.unpack_from(">I", data, box_start)
    if data[box_start + 4:box_start + 8] != b"ftyp":
        return None
    header_len = 8
    if size == 1:
        if box_start + 16 > len(data):
            return None
        (size,) = struct.unpack_from(">Q", data, box_start + 8)
        header_len = 16
    if size < header_len:
        return None

    pos = box_start + size
    limit = len(data)
    walked = 1
    while pos < limit and walked < 100000:
        if pos + 8 > limit:
            break  # trailing partial box -- stop; everything before here was validated
        (bsize,) = struct.unpack_from(">I", data, pos)
        hlen = 8
        if bsize == 0:
            pos = limit
            break
        if bsize == 1:
            if pos + 16 > limit:
                break
            (bsize,) = struct.unpack_from(">Q", data, pos + 8)
            hlen = 16
        if bsize < hlen:
            break
        pos += bsize
        walked += 1

    end = min(pos, limit)
    if end <= box_start:
        return None
    return (end, True)


def carve(name, data, i):
    """
    Dispatch to the right carver for SIGNATURES[name]. Returns
    {"end", "ext", "verified"} for an accepted candidate, or None if the
    candidate should be REJECTED outright (failed structural validation on
    a format where that's a strong sign of a false-positive match).
    """
    spec = SIGNATURES[name]
    header = spec["header"]
    header_len = len(header) if isinstance(header, bytes) else len(header[0])
    default_ext = spec["extensions"][0]
    carver = spec["carver"]

    if carver == "jpeg":
        result = _carve_footer_last(data, i, header_len, b"\xff\xd9", JPEG_MAX_BYTES)
        if result:
            end, verified = result
        else:
            end, verified = min(i + header_len + JPEG_MAX_BYTES, len(data)), False
        return {"end": end, "ext": default_ext, "verified": verified}

    if carver == "png":
        footer = spec["footer"]
        j = data.find(footer, i + header_len)
        if j >= 0:
            return {"end": j + len(footer), "ext": default_ext, "verified": True}
        end = min(i + header_len + UNVERIFIED_CAP_BYTES, len(data))
        return {"end": end, "ext": default_ext, "verified": False}

    if carver == "pdf":
        result = _carve_footer_last(data, i, header_len, b"%%EOF", PDF_MAX_BYTES)
        if result:
            end, verified = result
        else:
            end, verified = min(i + header_len + PDF_MAX_BYTES, len(data)), False
        return {"end": end, "ext": default_ext, "verified": verified}

    if carver == "zip":
        result = _carve_zip(data, i)
        if result is None:
            return None
        end, verified = result
        return {"end": end, "ext": default_ext, "verified": verified}

    if carver == "riff":
        result = _carve_riff(data, i)
        if result is None:
            return None
        end, ext, verified = result
        return {"end": end, "ext": ext, "verified": verified}

    if carver == "sqlite":
        result = _carve_sqlite(data, i)
        if result is None:
            return None
        end, verified = result
        return {"end": end, "ext": default_ext, "verified": verified}

    if carver == "bmp":
        result = _carve_bmp(data, i)
        if result is None:
            return None
        end, verified = result
        return {"end": end, "ext": default_ext, "verified": verified}

    if carver == "pe":
        result = _carve_pe(data, i)
        if result is None:
            return None
        end, verified = result
        return {"end": end, "ext": default_ext, "verified": verified}

    if carver == "elf":
        result = _carve_elf(data, i)
        if result is None:
            return None
        end, verified = result
        return {"end": end, "ext": default_ext, "verified": verified}

    if carver == "mp4":
        result = _carve_mp4(data, i)
        if result is None:
            return None
        end, verified = result
        return {"end": end, "ext": default_ext, "verified": verified}

    # "capped": no reliable end marker exists -- cut at the next header of
    # this same format, or the format's safety cap, whichever is smaller.
    nxt = data.find(header if isinstance(header, bytes) else header[0], i + header_len)
    cap = spec["max_size"] or UNVERIFIED_CAP_BYTES
    cap_end = nxt if nxt >= 0 else len(data)
    end = min(cap_end, i + cap, len(data))
    return {"end": end, "ext": default_ext, "verified": False}


def guess_format(blob):
    """If `blob` happens to start with a known signature, return its name
    (for a bonus cross-check on data recovered some other way, e.g. a
    filesystem-level undelete) -- otherwise None. Never used to CARVE, only
    to pick a validate() to try; callers must not treat a None here as
    proof of anything."""
    for name, spec in SIGNATURES.items():
        headers = spec["header"]
        if isinstance(headers, bytes):
            headers = (headers,)
        if any(blob.startswith(h) for h in headers):
            return name
    return None


def validate(name, blob, verified):
    """Returns "passed" | "partial" | "failed" | "unknown"."""
    try:
        if name in ("JPEG", "PNG", "GIF", "BMP", "TIFF"):
            return _validate_with_pillow(blob, verified)
        if name == "RIFF" and blob[8:12] == b"WAVE":
            return _validate_wav(blob)
        if name == "RIFF" and blob[8:12] == b"WEBP":
            return _validate_with_pillow(blob, verified)
        if name == "PDF":
            return _validate_pdf(blob)
        if name == "ZIP":
            return _validate_zip(blob)
        if name == "SQLITE":
            return _validate_sqlite(blob)
        if name == "GZIP":
            return _validate_gzip(blob)
    except Exception:
        return "failed"
    # PE/ELF/MP4/BMP/ZIP/RIFF/SQLITE were already structurally proven by carve()
    # itself when verified=True -- no separate check needed here.
    if verified and name in ("PE", "ELF", "MP4"):
        return "passed"
    return "unknown"


def _validate_with_pillow(blob, verified):
    try:
        from PIL import Image
    except ImportError:
        return "unknown"
    import io
    try:
        Image.open(io.BytesIO(blob)).verify()
        return "passed"
    except Exception:
        return "partial" if not verified else "failed"


def _validate_wav(blob):
    import io
    import wave
    try:
        with wave.open(io.BytesIO(blob), "rb") as w:
            w.getnframes()
        return "passed"
    except Exception:
        return "failed"


def _validate_pdf(blob):
    has_trailer = b"trailer" in blob or b"startxref" in blob
    ends_ok = blob.rstrip(b"\r\n \t").endswith(b"%%EOF")
    if has_trailer and ends_ok:
        return "passed"
    if ends_ok:
        return "partial"
    return "partial"


def _validate_zip(blob):
    import io
    import zipfile
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            bad = z.testzip()
            return "passed" if bad is None else "partial"
    except Exception:
        return "failed"


def _validate_sqlite(blob):
    import os
    import sqlite3
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(blob)
        con = sqlite3.connect(path)
        try:
            (result,) = con.execute("PRAGMA integrity_check").fetchone()
            return "passed" if result == "ok" else "partial"
        finally:
            con.close()
    except Exception:
        return "failed"
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def _validate_gzip(blob):
    import gzip
    import io
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(blob)) as g:
            while g.read(1024 * 1024):
                pass
        return "passed"
    except EOFError:
        return "partial"  # ran out of (capped) data mid-stream -- plausible, just cut off
    except Exception:
        return "failed"


def fragmentation_status(verified, validation, hit_cap):
    if verified:
        return "Likely partial" if validation == "failed" else "Likely complete"
    if hit_cap:
        return "Likely partial"
    return "Possibly fragmented" if validation != "failed" else "Unknown"
