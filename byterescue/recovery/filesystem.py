"""FAT12/16/32 filesystem-aware recovery.

Reads the actual on-disk directory structure (short 8.3 + VFAT long-name
entries) instead of searching for byte signatures -- this can find files a
signature/text scan misses or mis-carves, including DELETED entries whose
directory-entry metadata (name, size, starting cluster) often survives even
after the file content stops being guaranteed intact.

NTFS and exFAT are NOT implemented here -- probe() returns None for them
(and for anything else that isn't a recognizable FAT12/16/32 boot sector),
and callers must treat that as "unsupported", never as "no deleted files".

IMPORTANT LIMITATION -- read this before trusting a "deleted" result:
Deleting a file on FAT does two things: it marks the directory entry's
first byte 0xE5, AND it zeroes that file's entries in the FAT (the table
that links a file's clusters together in order). So a deleted entry
normally still tells you the file's name, size, and FIRST cluster, but NOT
the real order of its later clusters if it was fragmented. This module
therefore ASSUMES CONTIGUOUS allocation for deleted files (reads
ceil(size / cluster_size) clusters straight from the start cluster) --
exactly what classic FAT-undelete tools do, and exactly why they have
always struggled with fragmented deleted files. Every recovered deleted
item is labeled accordingly; this is never silently presented as certain.
"""

import struct

ATTR_READ_ONLY = 0x01
ATTR_HIDDEN = 0x02
ATTR_SYSTEM = 0x04
ATTR_VOLUME_ID = 0x08
ATTR_DIRECTORY = 0x10
ATTR_ARCHIVE = 0x20
ATTR_LONG_NAME = 0x0F

MAX_WALK_ENTRIES = 200_000
MAX_DIR_DEPTH = 32
MAX_CHAIN_CLUSTERS = 500_000


class RandomAccessSource:
    """Minimal seek+read wrapper. FAT walking only ever needs specific byte
    ranges (the boot sector, FAT tables, directory/data clusters) -- never
    the whole source or its total size up front -- so this works uniformly
    for a regular file OR a raw \\\\.\\PhysicalDriveN device path, unlike
    mmap (which needs a size Windows won't report for a device path)."""

    def __init__(self, path):
        self._f = open(path, "rb")

    def read_at(self, offset, length):
        self._f.seek(offset)
        return self._f.read(length)

    def close(self):
        self._f.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()


def probe(reader):
    """Parse the boot sector at offset 0 and determine FAT12/16/32 using
    Microsoft's own cluster-count algorithm (the on-disk 'FAT16   '/'FAT32
    ' string in the boot sector is informational only and not authoritative
    -- real FAT drivers, and this one, ignore it for type determination).
    Returns a BPB dict, or None if this isn't a FAT12/16/32 boot sector."""
    boot = reader.read_at(0, 512)
    if len(boot) < 512 or boot[510:512] != b"\x55\xAA":
        return None
    try:
        bytes_per_sec = struct.unpack_from("<H", boot, 11)[0]
        sec_per_clus = boot[13]
        rsvd_sec_cnt = struct.unpack_from("<H", boot, 14)[0]
        num_fats = boot[16]
        root_ent_cnt = struct.unpack_from("<H", boot, 17)[0]
        tot_sec16 = struct.unpack_from("<H", boot, 19)[0]
        fat_sz16 = struct.unpack_from("<H", boot, 22)[0]
        tot_sec32 = struct.unpack_from("<I", boot, 32)[0]
        fat_sz32 = struct.unpack_from("<I", boot, 36)[0]
        root_clus32 = struct.unpack_from("<I", boot, 44)[0]
    except struct.error:
        return None

    if bytes_per_sec not in (512, 1024, 2048, 4096):
        return None
    if sec_per_clus == 0 or (sec_per_clus & (sec_per_clus - 1)) != 0:
        return None
    if num_fats not in (1, 2):
        return None

    fat_sz = fat_sz16 if fat_sz16 != 0 else fat_sz32
    tot_sec = tot_sec16 if tot_sec16 != 0 else tot_sec32
    if fat_sz == 0 or tot_sec == 0:
        return None

    root_dir_sectors = ((root_ent_cnt * 32) + (bytes_per_sec - 1)) // bytes_per_sec
    data_sec = tot_sec - (rsvd_sec_cnt + num_fats * fat_sz + root_dir_sectors)
    if data_sec <= 0:
        return None
    count_of_clusters = data_sec // sec_per_clus
    if count_of_clusters == 0:
        return None

    if count_of_clusters < 4085:
        fat_type = "FAT12"
    elif count_of_clusters < 65525:
        fat_type = "FAT16"
    else:
        fat_type = "FAT32"

    bpb = {
        "fat_type": fat_type,
        "bytes_per_sec": bytes_per_sec,
        "sec_per_clus": sec_per_clus,
        "cluster_bytes": bytes_per_sec * sec_per_clus,
        "num_fats": num_fats,
        "fat_sz": fat_sz,
        "fat_start_offset": rsvd_sec_cnt * bytes_per_sec,
        "first_data_sector": rsvd_sec_cnt + num_fats * fat_sz + root_dir_sectors,
        "root_dir_sectors": root_dir_sectors,
        "count_of_clusters": count_of_clusters,
    }
    if fat_type == "FAT32":
        if root_clus32 < 2:
            return None
        bpb["root_clus"] = root_clus32
    else:
        bpb["root_first_sector"] = rsvd_sec_cnt + num_fats * fat_sz
    return bpb


def _cluster_offset(bpb, cluster):
    sector = bpb["first_data_sector"] + (cluster - 2) * bpb["sec_per_clus"]
    return sector * bpb["bytes_per_sec"]


def _next_cluster(reader, bpb, cluster):
    fat_type = bpb["fat_type"]
    fat_start = bpb["fat_start_offset"]
    if fat_type == "FAT32":
        raw = reader.read_at(fat_start + cluster * 4, 4)
        if len(raw) < 4:
            return None
        val = struct.unpack("<I", raw)[0] & 0x0FFFFFFF
        return None if (val == 0 or val >= 0x0FFFFFF8) else val
    if fat_type == "FAT16":
        raw = reader.read_at(fat_start + cluster * 2, 2)
        if len(raw) < 2:
            return None
        val = struct.unpack("<H", raw)[0]
        return None if (val == 0 or val >= 0xFFF8) else val
    # FAT12: 12-bit entries packed two-per-three-bytes
    off = fat_start + (cluster * 3) // 2
    raw = reader.read_at(off, 2)
    if len(raw) < 2:
        return None
    val = struct.unpack("<H", raw)[0]
    val = (val & 0x0FFF) if (cluster % 2 == 0) else (val >> 4)
    return None if (val == 0 or val >= 0xFF8) else val


def _cluster_chain(reader, bpb, start_cluster, max_clusters=MAX_CHAIN_CLUSTERS):
    """The REAL FAT chain -- only meaningful for entries that are NOT
    deleted. A deleted entry's chain is typically already zeroed; see
    read_entry_bytes() for how deleted files are handled instead."""
    cluster = start_cluster
    seen = set()
    n = 0
    while cluster is not None and cluster >= 2 and n < max_clusters:
        if cluster in seen:
            break  # cycle -- corrupt FAT, stop rather than loop forever
        seen.add(cluster)
        yield cluster
        cluster = _next_cluster(reader, bpb, cluster)
        n += 1


def _read_chain_bytes(reader, bpb, start_cluster, max_clusters=MAX_CHAIN_CLUSTERS):
    return b"".join(
        reader.read_at(_cluster_offset(bpb, c), bpb["cluster_bytes"])
        for c in _cluster_chain(reader, bpb, start_cluster, max_clusters)
    )


def _decode_short_name(raw11, deleted):
    base, ext = bytearray(raw11[0:8]), raw11[8:11]
    if deleted:
        # 0xE5 (the deletion marker) overwrote the real first character --
        # it cannot be recovered from the directory entry alone.
        base[0] = ord("?")
    elif base[0] == 0x05:
        base[0] = 0xE5  # escape for a legitimate leading 0xE5 character
    base_s = bytes(base).decode("cp437", errors="replace").rstrip()
    ext_s = ext.decode("cp437", errors="replace").rstrip()
    return f"{base_s}.{ext_s}" if ext_s else base_s


def _parse_dir_block(block):
    """One directory's raw bytes (root region or a cluster chain) -> a list
    of file/subdirectory entries, combining short 8.3 entries with any
    preceding VFAT long-name fragments, deleted entries included."""
    entries = []
    pending_lfn = {}
    i, n = 0, len(block)
    while i + 32 <= n:
        raw = block[i:i + 32]
        first = raw[0]
        if first == 0x00:
            break  # unused, and nothing after it was ever used either
        attr = raw[11]

        if attr == ATTR_LONG_NAME:
            if first != 0xE5:  # a deleted LFN fragment's ordinal is gone -- unusable
                ordv = first & ~0x40
                name_bytes = raw[1:11] + raw[14:26] + raw[28:32]
                try:
                    frag = name_bytes.decode("utf-16-le")
                except UnicodeDecodeError:
                    frag = ""
                cut = frag.find("\x00")
                pending_lfn[ordv] = frag if cut < 0 else frag[:cut]
            i += 32
            continue

        if (attr & ATTR_VOLUME_ID) and not (attr & ATTR_DIRECTORY):
            pending_lfn = {}
            i += 32
            continue  # volume label, not a file

        deleted = first == 0xE5
        short_name = _decode_short_name(raw[0:11], deleted)
        name = "".join(pending_lfn[k] for k in sorted(pending_lfn)) if pending_lfn else short_name
        pending_lfn = {}

        clus_hi = struct.unpack_from("<H", raw, 20)[0]
        clus_lo = struct.unpack_from("<H", raw, 26)[0]
        first_cluster = (clus_hi << 16) | clus_lo
        size = struct.unpack_from("<I", raw, 28)[0]

        if name not in (".", ".."):
            entries.append({
                "name": name, "short_name": short_name, "deleted": deleted,
                "is_dir": bool(attr & ATTR_DIRECTORY), "first_cluster": first_cluster,
                "size": size, "attr": attr,
            })
        i += 32
    return entries


def walk(reader, bpb, max_entries=MAX_WALK_ENTRIES):
    """Depth-first list of every file/subdirectory entry (deleted or not),
    each with a '/'-joined `path` built from the directories walked to
    reach it."""
    if bpb["fat_type"] == "FAT32":
        root_bytes = _read_chain_bytes(reader, bpb, bpb["root_clus"])
    else:
        off = bpb["root_first_sector"] * bpb["bytes_per_sec"]
        root_bytes = reader.read_at(off, bpb["root_dir_sectors"] * bpb["bytes_per_sec"])

    results = []
    _walk_dir_bytes(reader, bpb, root_bytes, "", results, max_entries, depth=0)
    return results


def _walk_dir_bytes(reader, bpb, dir_bytes, path_prefix, results, max_entries, depth):
    if depth > MAX_DIR_DEPTH or len(results) >= max_entries:
        return
    for e in _parse_dir_block(dir_bytes):
        if len(results) >= max_entries:
            return
        e["path"] = f"{path_prefix}/{e['name']}" if path_prefix else e["name"]
        results.append(e)
        if e["is_dir"] and e["first_cluster"] >= 2:
            try:
                if e["deleted"]:
                    # The subdirectory's own chain is usually zeroed too --
                    # only its first cluster can be attempted, best-effort.
                    sub_bytes = reader.read_at(_cluster_offset(bpb, e["first_cluster"]), bpb["cluster_bytes"])
                else:
                    sub_bytes = _read_chain_bytes(reader, bpb, e["first_cluster"])
            except Exception:
                continue  # unreadable/corrupt subdirectory -- skip it, don't abort the whole walk
            _walk_dir_bytes(reader, bpb, sub_bytes, e["path"], results, max_entries, depth + 1)


def read_entry_bytes(reader, bpb, entry):
    """Returns (data, chain_verified). chain_verified=True means the real
    FAT chain was followed (only possible for a non-deleted entry);
    chain_verified=False means contiguous allocation was ASSUMED from the
    known start cluster (the only option for a deleted entry) -- treat
    that data as unconfirmed beyond the first cluster."""
    size = entry["size"]
    if entry["first_cluster"] < 2 or size == 0:
        return b"", False
    if entry["deleted"]:
        n_clusters = (size + bpb["cluster_bytes"] - 1) // bpb["cluster_bytes"]
        n_clusters = min(n_clusters, MAX_CHAIN_CLUSTERS)
        cluster = entry["first_cluster"]
        parts = []
        for _ in range(n_clusters):
            parts.append(reader.read_at(_cluster_offset(bpb, cluster), bpb["cluster_bytes"]))
            cluster += 1  # ASSUMPTION: contiguous allocation, see module docstring
        return b"".join(parts)[:size], False
    data = _read_chain_bytes(reader, bpb, entry["first_cluster"])
    return data[:size], True
