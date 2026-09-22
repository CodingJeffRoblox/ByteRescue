"""Educational hex/byte reference used by the Hex Viewer's lookup and
click-a-line features. NEVER imported by the scanner -- see signatures.py
for what actually drives carving. Keeping this in its own module makes that
separation explicit instead of just a comment.
"""

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
    "42 4D": "BMP file header ('BM'). Only 2 bytes, so on its own this is a weak/common pattern -- BMP also stores its exact file size as a 4-byte field right after these 2 bytes, which the scanner uses to carve it reliably",
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
    "4D 5A": "MZ header ('MZ', Windows/DOS executable). Only 2 bytes -- far too common to use alone; the scanner requires this PLUS a validated 'PE\\0\\0' header located via the pointer stored in the DOS header",
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
