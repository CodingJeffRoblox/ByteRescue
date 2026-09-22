"""Text-file recovery.

Plain text has no universal magic header, so this does not belong in
signatures.py -- instead of a header/footer pair, it looks for long runs of
plausible human-readable bytes (ASCII/UTF-8, UTF-16 LE, UTF-16 BE) and scores
each run's confidence. Low-confidence runs (mostly-binary data that happens
to contain a few printable bytes) are rejected, not reported.
"""

import re

DEFAULT_MIN_LENGTH = 80        # shorter runs aren't worth reporting as "a text file"
MERGE_GAP = 48                 # merge runs separated by a short non-text gap (one bad byte, etc.)
CONFIDENCE_REJECT_BELOW = 0.55
PREVIEW_RAW_CAP = 2000         # bytes of each candidate kept in memory for the preview

_TEXT_BYTE = rb"[\t\n\r\x20-\x7e]"
_re_cache = {}


def _compiled(kind, min_length):
    key = (kind, min_length)
    r = _re_cache.get(key)
    if r is not None:
        return r
    if kind == "ascii":
        r = re.compile(_TEXT_BYTE + rb"{%d,}" % min_length)
    elif kind == "utf16le":
        r = re.compile(rb"(?:" + _TEXT_BYTE + rb"\x00){%d,}" % max(1, min_length // 2))
    else:  # utf16be
        r = re.compile(rb"(?:\x00" + _TEXT_BYTE + rb"){%d,}" % max(1, min_length // 2))
    _re_cache[key] = r
    return r


def _confidence_ascii(sample):
    # Weighted toward letters/digits/common punctuation, not just "any printable
    # byte", so a long run of e.g. repeated symbols doesn't score as confident text.
    if not sample:
        return 0.0
    n = len(sample)
    good = sum(1 for b in sample if 48 <= b <= 57 or 65 <= b <= 90 or 97 <= b <= 122
               or b in b" \t\n\r.,;:!?'\"-()")
    ratio = good / n
    length_bonus = min(n / 2000, 1.0) * 0.15
    return max(0.0, min(1.0, ratio * 0.85 + length_bonus))


def _merge_spans(spans, gap):
    if not spans:
        return []
    spans = sorted(spans)
    merged = [list(spans[0])]
    for s, e in spans[1:]:
        if s - merged[-1][1] <= gap:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


def find_candidates(buf, base_offset=0, min_length=DEFAULT_MIN_LENGTH):
    """Scan an in-memory buffer/bytes-like object for plausible text runs.

    Returns a list of dicts: offset (absolute), length, encoding, confidence
    (0..1), preview_raw (a capped byte sample for building a preview).
    Runs below CONFIDENCE_REJECT_BELOW are left out entirely.
    """
    candidates = []

    ascii_spans = [(m.start(), m.end()) for m in _compiled("ascii", min_length).finditer(buf)]
    for s, e in _merge_spans(ascii_spans, MERGE_GAP):
        sample = bytes(buf[s:e])
        conf = _confidence_ascii(sample)
        if conf < CONFIDENCE_REJECT_BELOW:
            continue
        encoding = "UTF-8" if any(b >= 0x80 for b in sample) else "ASCII"
        try:
            sample.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            encoding = "ASCII (stray non-UTF-8 bytes)"
        candidates.append({
            "offset": base_offset + s, "length": e - s, "encoding": encoding,
            "confidence": conf, "preview_raw": sample[:PREVIEW_RAW_CAP],
        })

    for kind, label, decode_name in (("utf16le", "UTF-16 LE", "utf-16-le"),
                                      ("utf16be", "UTF-16 BE", "utf-16-be")):
        spans = [(m.start(), m.end()) for m in _compiled(kind, min_length).finditer(buf)]
        for s, e in _merge_spans(spans, MERGE_GAP * 2):
            sample = bytes(buf[s:e])
            try:
                text = sample.decode(decode_name)
            except UnicodeDecodeError:
                continue
            printable = sum(1 for ch in text if ch.isprintable() or ch in "\t\n\r")
            conf = printable / max(1, len(text))
            if conf < CONFIDENCE_REJECT_BELOW:
                continue
            candidates.append({
                "offset": base_offset + s, "length": e - s, "encoding": label,
                "confidence": conf, "preview_raw": sample[:PREVIEW_RAW_CAP],
            })

    candidates.sort(key=lambda c: c["offset"])
    return candidates


def preview_text(candidate, max_chars=400):
    encoding = candidate["encoding"]
    raw = candidate["preview_raw"]
    if encoding.startswith("UTF-16 LE"):
        text = raw.decode("utf-16-le", errors="replace")
    elif encoding.startswith("UTF-16 BE"):
        text = raw.decode("utf-16-be", errors="replace")
    else:
        text = raw.decode("utf-8", errors="replace")
    return text[:max_chars]
