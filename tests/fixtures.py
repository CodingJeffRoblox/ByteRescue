"""Synthetic test fixtures -- built in memory, never real user files."""

import io
import sqlite3
import struct
import tempfile
import wave
import zipfile
import zlib
import gzip as gzip_module
import os


def jpeg_with_embedded_thumbnail():
    """A JPEG whose EXIF-like APP1 segment contains its own tiny JPEG
    (thumbnail) with an earlier EOI -- the case _carve_footer_last exists
    to handle correctly instead of truncating at the thumbnail's EOI."""
    thumb = b"\xff\xd8\xff\xe1" + b"\x00" * 20 + b"\xff\xd9"
    main = b"\xff\xd8\xff\xe0" + thumb + b"\x00" * 50 + b"\xff\xd9"
    return main


def png_bytes():
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
    raw = b"\x00" + b"\xff\x00\x00" * 2  # one scanline, filter byte + 2 red pixels
    idat = chunk(b"IDAT", zlib.compress(raw * 2))
    iend = chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


def pdf_with_incremental_update():
    body1 = b"%PDF-1.4\n1 0 obj\n<< >>\nendobj\ntrailer\n<< >>\n%%EOF\n"
    body2 = b"2 0 obj\n<< >>\nendobj\ntrailer\n<< >>\nstartxref\n0\n%%EOF"
    return body1 + body2


def multi_entry_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("a.txt", "hello world " * 50)
        z.writestr("b.txt", "second entry " * 50)
        z.writestr("c/data.bin", bytes(range(256)) * 4)
    return buf.getvalue()


def docx_like_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", "<document/>")
    return buf.getvalue()


def gzip_bytes():
    return gzip_module.compress(b"hello world " * 200)


def wav_bytes():
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x01" * 1000)
    return buf.getvalue()


def sqlite_bytes():
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    os.remove(path)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE t(x INTEGER)")
    for i in range(50):
        con.execute("INSERT INTO t VALUES (?)", (i,))
    con.commit()
    con.close()
    with open(path, "rb") as f:
        data = f.read()
    os.remove(path)
    return data


def bmp_bytes():
    width, height = 2, 2
    row_size = ((width * 3 + 3) // 4) * 4
    row = (b"\x00\x00\xff\x00\xff\x00" + b"\x00" * (row_size - 6))
    pixel_data = row * height
    dib_size = 40
    pixel_offset = 14 + dib_size
    file_size = pixel_offset + len(pixel_data)
    header = b"BM" + struct.pack("<IHHI", file_size, 0, 0, pixel_offset)
    dib = struct.pack("<IiiHHIIiiII", dib_size, width, height, 1, 24, 0, len(pixel_data), 2835, 2835, 0, 0)
    return header + dib + pixel_data


def pe_bytes():
    """A minimal but structurally real PE32: DOS header -> PE\\0\\0 ->
    COFF file header -> a full-size (mostly zeroed) optional header ->
    one section header -> that section's raw bytes."""
    e_lfanew = 64
    dos = b"MZ" + b"\x00" * 58 + struct.pack("<I", e_lfanew)
    file_header = struct.pack("<HHIIIHH", 0x014C, 1, 0, 0, 0, 224, 0x0102)
    opt_header = struct.pack("<H", 0x10B) + b"\x00" * (224 - 2)
    section_table_rel = 4 + len(file_header) + len(opt_header)  # offset from e_lfanew
    ptr_raw = e_lfanew + section_table_rel + 40
    section_data = b"\x90" * 128
    section = (
        b".text\x00\x00\x00"
        + struct.pack("<IIII", len(section_data), 0x1000, len(section_data), ptr_raw)
        + struct.pack("<IIHHI", 0, 0, 0, 0, 0x60000020)
    )
    pe = dos + b"PE\x00\x00" + file_header + opt_header + section
    pe += b"\x00" * max(0, ptr_raw - len(pe))
    pe += section_data
    return pe


def elf64_bytes():
    header = bytearray(64)
    header[0:4] = b"\x7fELF"
    header[4] = 2  # ELFCLASS64
    header[5] = 1  # little-endian
    header[6] = 1  # EI_VERSION
    struct.pack_into("<H", header, 16, 2)     # e_type
    struct.pack_into("<H", header, 18, 0x3E)  # e_machine (x86-64)
    struct.pack_into("<I", header, 20, 1)     # e_version
    struct.pack_into("<Q", header, 40, 64)    # e_shoff -- right after this header
    struct.pack_into("<H", header, 52, 64)    # e_ehsize
    struct.pack_into("<H", header, 58, 64)    # e_shentsize
    struct.pack_into("<H", header, 60, 1)     # e_shnum
    section_header = b"\x00" * 64
    return bytes(header) + section_header


def mp4_bytes():
    def box(btype, payload):
        return struct.pack(">I", 8 + len(payload)) + btype + payload

    ftyp = box(b"ftyp", b"isom" + struct.pack(">I", 0) + b"isomiso2avc1mp41")
    moov = box(b"moov", b"\x00" * 40)
    mdat = box(b"mdat", b"\x01" * 200)
    return ftyp + moov + mdat


def ascii_text():
    return b"Hello Daniel,\r\nThis is a plain ASCII test file with normal punctuation.\r\n" * 5


def utf8_text():
    return ("Café naïve résumé -- some UTF-8 accented text for testing.\n" * 5).encode("utf-8")


def utf16le_text():
    return ("Hello from UTF-16 LE. This should be detected as readable text.\n" * 5).encode("utf-16-le")


def utf16be_text():
    return ("Hello from UTF-16 BE. This should be detected as readable text.\n" * 5).encode("utf-16-be")


# ---------------------------------------------------------------------------
# Synthetic FAT filesystem images, built by hand from the spec (not with a
# real mkfs tool) so the exact bytes -- and therefore what filesystem.py is
# actually being tested against -- are fully known and controlled.
# ---------------------------------------------------------------------------

def _sfn(name8, ext3):
    return name8.ljust(8)[:8].encode("ascii") + ext3.ljust(3)[:3].encode("ascii")


def _lfn_checksum(short_name_11):
    s = 0
    for b in short_name_11:
        s = (((s & 1) << 7) | (s >> 1)) + b
        s &= 0xFF
    return s


def _lfn_entries(long_name, short_name_11):
    """Build the VFAT long-name entries (in on-disk storage order: last
    logical part first) that must precede a short entry for `long_name`."""
    chksum = _lfn_checksum(short_name_11)
    chars = long_name + "\x00"
    parts = [chars[i:i + 13] for i in range(0, len(chars), 13)] or [""]
    if len(parts[-1]) < 13:
        parts[-1] = parts[-1] + "\xff" * (13 - len(parts[-1]))
    entries = []
    total = len(parts)
    for idx, part in enumerate(parts):
        seq = idx + 1
        ordv = seq | (0x40 if seq == total else 0)
        n1, n2, n3 = part[0:5], part[5:11], part[11:13]
        raw = bytes([ordv]) + n1.encode("utf-16-le") + bytes([ATTR_LONG_NAME, 0, chksum]) \
            + n2.encode("utf-16-le") + b"\x00\x00" + n3.encode("utf-16-le")
        entries.append(raw)
    entries.reverse()  # stored highest-sequence-first
    return entries


ATTR_LONG_NAME = 0x0F
ATTR_DIRECTORY = 0x10
ATTR_ARCHIVE = 0x20
FAT16_END = 0xFFFF
FAT32_END = 0x0FFFFFFF


def _short_entry(name8, ext3, attr, first_cluster, size, deleted=False):
    raw = bytearray(32)
    raw[0:11] = _sfn(name8, ext3)
    if deleted:
        raw[0] = 0xE5
    raw[11] = attr
    struct.pack_into("<H", raw, 20, (first_cluster >> 16) & 0xFFFF)
    struct.pack_into("<H", raw, 26, first_cluster & 0xFFFF)
    struct.pack_into("<I", raw, 28, size)
    return bytes(raw)


def build_fat16_image():
    """A tiny (a few KB) but spec-correct FAT16 image: BPB claims enough
    total sectors to land in the real FAT16 cluster-count range (the type
    is determined purely by cluster count, per the Microsoft algorithm --
    not by any on-disk 'FAT16   ' label), while the image itself only
    physically contains the handful of sectors actually used below."""
    bytes_per_sec = 512
    sec_per_clus = 1
    rsvd_sec_cnt = 1
    num_fats = 2
    root_ent_cnt = 16
    fat_sz16 = 1
    tot_sec32 = 6000  # -> count_of_clusters = 5996, squarely in the FAT16 range

    boot = bytearray(512)
    boot[0:3] = b"\xeb\x3c\x90"
    struct.pack_into("<H", boot, 11, bytes_per_sec)
    boot[13] = sec_per_clus
    struct.pack_into("<H", boot, 14, rsvd_sec_cnt)
    boot[16] = num_fats
    struct.pack_into("<H", boot, 17, root_ent_cnt)
    struct.pack_into("<H", boot, 19, 0)  # tot_sec16 = 0 -> use tot_sec32
    struct.pack_into("<H", boot, 22, fat_sz16)
    struct.pack_into("<I", boot, 32, tot_sec32)
    boot[38] = 0x29  # BS_BootSig
    boot[54:62] = b"FAT16   "
    boot[510:512] = b"\x55\xAA"

    fat1 = bytearray(bytes_per_sec)
    fat2 = bytearray(bytes_per_sec)

    def set_fat16(cluster, value):
        struct.pack_into("<H", fat1, cluster * 2, value)

    hello_content = b"Hello FAT16 World!"
    big_content = (b"X" * 512) + (b"Y" * 88)  # spans clusters 3 and 4
    deleted_content = b"This file was deleted but the bytes are still here."
    nested_content = b"A file inside a subdirectory."
    long_name = "This is a long filename that needs VFAT entries.txt"
    long_short = _sfn("THISIS~1", "TXT")

    set_fat16(2, FAT16_END)          # HELLO.TXT (1 cluster)
    set_fat16(3, 4)                  # BIG.BIN cluster 1 -> cluster 2
    set_fat16(4, FAT16_END)          # BIG.BIN cluster 2 (end)
    set_fat16(5, 0)                  # deleted file's cluster: FAT freed at deletion time
    set_fat16(6, FAT16_END)          # SUBDIR (1 cluster)
    set_fat16(7, FAT16_END)          # NESTED.TXT inside SUBDIR
    set_fat16(8, FAT16_END)          # long-named file

    root = bytearray(root_ent_cnt * 32)
    entries = [
        _short_entry("HELLO", "TXT", ATTR_ARCHIVE, 2, len(hello_content)),
        _short_entry("BIG", "BIN", ATTR_ARCHIVE, 3, len(big_content)),
        _short_entry("DELETED", "TXT", ATTR_ARCHIVE, 5, len(deleted_content), deleted=True),
        _short_entry("SUBDIR", "", ATTR_DIRECTORY, 6, 0),
    ]
    long_entries = _lfn_entries(long_name, long_short)
    pos = 0
    root[pos:pos + 32] = entries[0]; pos += 32
    root[pos:pos + 32] = entries[1]; pos += 32
    root[pos:pos + 32] = entries[2]; pos += 32
    root[pos:pos + 32] = entries[3]; pos += 32
    for lfn in long_entries:
        root[pos:pos + 32] = lfn; pos += 32
    root[pos:pos + 32] = _short_entry("THISIS~1", "TXT", ATTR_ARCHIVE, 8, 0); pos += 32

    subdir = bytearray(bytes_per_sec)
    sp = 0
    subdir[sp:sp + 32] = _short_entry(".", "", ATTR_DIRECTORY, 6, 0); sp += 32
    subdir[sp:sp + 32] = _short_entry("..", "", ATTR_DIRECTORY, 0, 0); sp += 32
    subdir[sp:sp + 32] = _short_entry("NESTED", "TXT", ATTR_ARCHIVE, 7, len(nested_content)); sp += 32

    # Layout: sector 0 boot, 1-2 FATs, 3 root dir, 4.. data (cluster N -> sector N+2)
    image = bytearray(10 * bytes_per_sec)
    image[0:512] = boot
    image[512:1024] = fat1
    image[1024:1536] = fat2
    image[1536:1536 + len(root)] = root

    def put_cluster(cluster, data):
        off = (cluster + 2) * bytes_per_sec
        image[off:off + len(data)] = data.ljust(bytes_per_sec, b"\x00")[:bytes_per_sec] if len(data) < bytes_per_sec else data[:bytes_per_sec]

    put_cluster(2, hello_content)
    put_cluster(3, big_content[:512])
    put_cluster(4, big_content[512:])
    put_cluster(5, deleted_content)
    put_cluster(6, bytes(subdir))
    put_cluster(7, nested_content)

    return bytes(image), {
        "hello_content": hello_content, "big_content": big_content,
        "deleted_content": deleted_content, "nested_content": nested_content,
        "long_name": long_name,
    }


def build_fat32_image():
    """A minimal FAT32 image exercising the FAT32-only code paths: 32-bit
    FAT entries and a cluster-chain (not fixed-region) root directory. The
    BPB claims a large enough volume to classify as FAT32 by cluster count
    while the image itself stays small -- see build_fat16_image()."""
    bytes_per_sec = 512
    sec_per_clus = 1
    rsvd_sec_cnt = 32
    num_fats = 2
    fat_sz32 = 8
    root_clus = 2
    tot_sec32 = 600000  # -> count_of_clusters well past 65525, squarely FAT32

    boot = bytearray(512)
    boot[0:3] = b"\xeb\x58\x90"
    struct.pack_into("<H", boot, 11, bytes_per_sec)
    boot[13] = sec_per_clus
    struct.pack_into("<H", boot, 14, rsvd_sec_cnt)
    boot[16] = num_fats
    struct.pack_into("<H", boot, 17, 0)       # root_ent_cnt = 0 for FAT32
    struct.pack_into("<H", boot, 19, 0)
    struct.pack_into("<H", boot, 22, 0)       # fat_sz16 = 0 for FAT32
    struct.pack_into("<I", boot, 32, tot_sec32)
    struct.pack_into("<I", boot, 36, fat_sz32)
    struct.pack_into("<I", boot, 44, root_clus)
    boot[66] = 0x29
    boot[82:90] = b"FAT32   "
    boot[510:512] = b"\x55\xAA"

    fat_start = rsvd_sec_cnt * bytes_per_sec
    fat_bytes = bytearray(fat_sz32 * bytes_per_sec)

    def set_fat32(cluster, value):
        struct.pack_into("<I", fat_bytes, cluster * 4, value & 0x0FFFFFFF)

    file_content = b"Hello FAT32 World -- this is the root-cluster-chain path."
    set_fat32(root_clus, FAT32_END)       # root directory, 1 cluster
    set_fat32(3, FAT32_END)               # ROOTFILE.TXT

    root = bytearray(bytes_per_sec)
    rp = 0
    root[rp:rp + 32] = _short_entry(".", "", ATTR_DIRECTORY, root_clus, 0); rp += 32
    root[rp:rp + 32] = _short_entry("..", "", ATTR_DIRECTORY, 0, 0); rp += 32
    root[rp:rp + 32] = _short_entry("ROOTFILE", "TXT", ATTR_ARCHIVE, 3, len(file_content)); rp += 32

    first_data_sector = rsvd_sec_cnt + num_fats * fat_sz32  # root_dir_sectors=0 for FAT32
    data_start = first_data_sector * bytes_per_sec

    image = bytearray(data_start + 2 * bytes_per_sec)
    image[0:512] = boot
    image[fat_start:fat_start + len(fat_bytes)] = fat_bytes
    # No second FAT copy written: _next_cluster() only ever reads FAT copy 1
    # (at fat_start_offset), so a copy 2 would add nothing but risk of a
    # slice-assignment bug (an earlier draft of this fixture had exactly
    # that bug -- writing it at a zero-length slice silently inserted bytes
    # and shifted the whole data area instead of overwriting anything).

    def put_cluster(cluster, data):
        off = data_start + (cluster - 2) * bytes_per_sec
        image[off:off + len(data)] = data

    put_cluster(root_clus, bytes(root))
    put_cluster(3, file_content)

    return bytes(image), {"file_content": file_content}
