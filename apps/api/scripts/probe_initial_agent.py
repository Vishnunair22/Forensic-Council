"""
Test helper utilities for system-level agent integration tests.

Provides factory functions for creating synthetic evidence files
(images, audio, video) used by the full-stack agent smoke tests.
"""

from __future__ import annotations

import struct
import wave
from io import BytesIO
from pathlib import Path


def _create_jpeg(file_path: str | Path) -> None:
    """Create a minimal valid JPEG file (1x1 pixel white)."""
    path = Path(file_path)
    # Minimal JPEG: SOI + APP0 + SOF0 + SOS + EOI
    raw = b""
    raw += b"\xff\xd8"  # SOI
    raw += b"\xff\xe0"  # APP0
    raw += struct.pack(">H", 16)  # length
    raw += b"JFIF\x00"  # identifier
    raw += b"\x01\x01"  # version
    raw += b"\x00"  # units
    raw += struct.pack(">HH", 1, 1)  # x/y density
    raw += b"\x00\x00"  # thumbnail
    raw += b"\xff\xdb"  # DQT
    raw += struct.pack(">H", 67)  # length
    raw += b"\x00"  # precision
    raw += b"\x08" * 64  # quantization table
    raw += b"\xff\xc0"  # SOF0
    raw += struct.pack(">H", 11)  # length
    raw += b"\x08"  # precision
    raw += struct.pack(">HH", 1, 1)  # height, width
    raw += b"\x01"  # number of components
    raw += b"\x01\x11\x00"  # component info
    raw += b"\xff\xc4"  # DHT
    raw += struct.pack(">H", 19)  # length
    raw += b"\x00"  # table class/id
    raw += b"\x00" * 16  # counts
    raw += b"\x00"  # symbols
    raw += b"\xff\xda"  # SOS
    raw += struct.pack(">H", 8)  # length
    raw += b"\x01\x01"  # component
    raw += b"\x00\x00\x3f\x00"  # spectral selection
    raw += b"\x02"  # entropy-coded data
    raw += b"\xff\xd9"  # EOI
    path.write_bytes(raw)


def _create_png(file_path: str | Path) -> None:
    """Create a minimal valid PNG file (1x1 pixel white)."""
    path = Path(file_path)

    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        length = struct.pack(">I", len(data))
        crc_data = chunk_type + data
        import zlib
        crc = struct.pack(">I", zlib.crc32(crc_data) & 0xFFFFFFFF)
        return length + crc_data + crc

    raw = b"\x89PNG\r\n\x1a\n"
    raw += _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    import zlib
    raw += _chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff"))
    raw += _chunk(b"IEND", b"")
    path.write_bytes(raw)


def _create_wav(file_path: str | Path) -> None:
    """Create a minimal valid WAV file (1 second of 440Hz sine at 16-bit 44.1kHz)."""
    path = Path(file_path)
    import math
    sample_rate = 44100
    duration = 1
    num_samples = sample_rate * duration
    samples = []
    for i in range(num_samples):
        sample = int(16000 * math.sin(2 * math.pi * 440 * i / sample_rate))
        samples.append(sample)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack("<" + "h" * num_samples, *samples))


def _create_mp4(file_path: str | Path) -> None:
    """Create a minimal valid MP4 file (FTYP + MOOV boxes)."""
    path = Path(file_path)
    # Minimal ISO BMFF (MP4) with just ftyp and moov boxes
    ftyp = b"isom" + struct.pack(">I", 0x200) + b"isom" + b"iso2" + b"mp41"
    ftyp_box = struct.pack(">I", 8 + len(ftyp)) + b"ftyp" + ftyp

    # Minimal moov box with a single track
    mdhd = struct.pack(">I", 32) + b"mdhd"
    mdhd += struct.pack(">I", 0)  # version + flags
    mdhd += struct.pack(">I", 0)  # creation time
    mdhd += struct.pack(">I", 0)  # modification time
    mdhd += struct.pack(">I", 1000)  # timescale
    mdhd += struct.pack(">I", 0)  # duration
    mdhd += b"\x55\xc4"  # language (undetermined)
    mdhd += b"\x00\x00"  # pre-defined

    hdlr = struct.pack(">I", 33) + b"hdlr"
    hdlr += struct.pack(">I", 0)  # version + flags
    hdlr += struct.pack(">I", 0)  # pre-defined
    hdlr += b"vide"  # handler type
    hdlr += struct.pack(">I", 0)  # reserved
    hdlr += struct.pack(">I", 0)  # reserved
    hdlr += struct.pack(">I", 0)  # reserved
    hdlr += b"VideoHandler\x00"  # name

    vmhd = struct.pack(">I", 20) + b"vmhd"
    vmhd += struct.pack(">I", 0x01)  # version + flags
    vmhd += b"\x00\x00\x00\x00\x00\x00\x00\x00"  # reserved

    stbl_data = struct.pack(">I", 16) + b"stsd"
    stbl_data += struct.pack(">I", 0)  # version + flags
    stbl_data += struct.pack(">I", 1)  # entry count
    stbl_data += struct.pack(">I", 0)  # empty sample entry

    stbl = struct.pack(">I", 8 + len(stbl_data)) + b"stbl" + stbl_data

    minf = struct.pack(">I", 8 + len(vmhd) + len(stbl)) + b"minf" + vmhd + stbl
    mdia = struct.pack(">I", 8 + len(mdhd) + len(hdlr) + len(minf)) + b"mdia" + mdhd + hdlr + minf

    trak_data = mdia
    trak = struct.pack(">I", 8 + len(trak_data)) + b"trak" + trak_data

    mvhd = struct.pack(">I", 108) + b"mvhd"
    mvhd += struct.pack(">I", 0)  # version + flags
    mvhd += struct.pack(">I", 0)  # creation time
    mvhd += struct.pack(">I", 0)  # modification time
    mvhd += struct.pack(">I", 1000)  # timescale
    mvhd += struct.pack(">I", 0)  # duration
    mvhd += b"\x00\x01\x00\x00"  # rate
    mvhd += b"\x01\x00"  # volume
    mvhd += b"\x00" * 10  # reserved
    mvhd += b"\x00" * 36  # matrix
    mvhd += b"\x00" * 24  # pre-defined

    moov = struct.pack(">I", 8 + len(mvhd) + len(trak)) + b"moov" + mvhd + trak

    path.write_bytes(ftyp_box + moov)
