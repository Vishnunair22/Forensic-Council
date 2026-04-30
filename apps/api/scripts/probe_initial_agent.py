"""Small evidence fixtures used by system probe tests.

The helpers intentionally avoid network access and heavyweight encoders so
pytest can collect and run on a clean clone.
"""

from __future__ import annotations

import math
import wave
from pathlib import Path

from PIL import Image, ImageDraw


def _create_png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (96, 72), color=(22, 32, 48))
    draw = ImageDraw.Draw(image)
    draw.rectangle((18, 16, 78, 56), outline=(80, 220, 180), width=3)
    draw.text((24, 28), "FC", fill=(240, 245, 255))
    image.save(path, format="PNG")


def _create_jpeg(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (96, 72), color=(35, 40, 55))
    draw = ImageDraw.Draw(image)
    draw.ellipse((20, 14, 76, 58), outline=(255, 210, 90), width=3)
    draw.text((36, 28), "J", fill=(255, 255, 255))
    image.save(path, format="JPEG", quality=90)


def _create_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = 16_000
    duration_s = 1.0
    amplitude = 10_000
    frames = bytearray()
    for i in range(int(sample_rate * duration_s)):
        sample = int(amplitude * math.sin(2 * math.pi * 440 * (i / sample_rate)))
        frames.extend(sample.to_bytes(2, byteorder="little", signed=True))

    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(bytes(frames))


def _create_mp4(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Minimal MP4-like container header. Tools that require a full video may
    # mark it incomplete, but collection and MIME-path tests can proceed.
    path.write_bytes(
        b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"
        b"\x00\x00\x00\x08free"
        b"\x00\x00\x00\x10mdat"
        b"forensic-council"
    )
