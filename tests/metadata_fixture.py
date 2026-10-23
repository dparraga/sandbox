"""Authored metadata-only fixtures; no private photograph or image payload."""

import struct


def box(kind, payload):
    return struct.pack(">I4s", len(payload) + 8, kind) + payload


def tiff_metadata(date="2030:02:03 04:05:06", offset="+02:30", subsec="123456", *, nontext=False, cycle=False):
    values = [(0x9003, date), (0x9011, offset), (0x9291, subsec)]
    values = [(tag, value) for tag, value in values if value is not None]
    # IFD0 points to the Exif IFD; all offsets are relative to TIFF start.
    exif_offset = 26
    data_offset = exif_offset + 2 + len(values) * 12 + 4
    entries, data = [], b""
    for tag, value in values:
        if nontext and tag == 0x9003:
            entries.append(struct.pack("<HHI", tag, 3, 1) + struct.pack("<H", 7) + b"\0\0")
            continue
        encoded = value.encode("ascii") + b"\0"
        if len(encoded) <= 4:
            payload = encoded.ljust(4, b"\0")
        else:
            payload = struct.pack("<I", data_offset + len(data))
            data += encoded
        entries.append(struct.pack("<HHI", tag, 2, len(encoded)) + payload)
    return (b"II*\0" + struct.pack("<I", 8) + struct.pack("<H", 1)
            + struct.pack("<HHII", 0x8769, 4, 1, exif_offset)
            + struct.pack("<I", 8 if cycle else 0)
            + struct.pack("<H", len(values)) + b"".join(entries) + b"\0" * 4 + data)


def heif_metadata(**kwargs):
    ftyp = box(b"ftyp", b"heic" + b"\0" * 4 + b"heic")
    infe = box(b"infe", b"\x02\0\0\0" + struct.pack(">HH", 1, 0) + b"Exif\0")
    iinf = box(b"iinf", b"\0" * 4 + struct.pack(">H", 1) + infe)
    def meta(position):
        iloc = box(b"iloc", b"\0" * 4 + b"\x44\0" + struct.pack(">HHHHII", 1, 1, 0, 1, position, 0))
        return box(b"meta", b"\0" * 4 + iinf + iloc)
    provisional = meta(0)
    location = len(ftyp) + len(provisional) + 8
    payload = struct.pack(">I", 6) + b"Exif\0\0" + tiff_metadata(**kwargs)
    return ftyp + meta(location) + box(b"mdat", payload)


def huge_header_read():
    """HEIF Exif header offset requests nearly 4 GiB before TIFF parsing."""
    data = bytearray(heif_metadata())
    position = data.index(b"mdat") + 4
    data[position:position + 4] = struct.pack(">I", 0xFFFFFFFF)
    return bytes(data)


def nonprogressing_box():
    """Box length one byte repeatedly revisits/overlaps earlier box bytes."""
    return box(b"ftyp", b"heic" + b"\0" * 4 + b"heic") + struct.pack(">I4s", 1, b"junk") + b"\0" * 8
