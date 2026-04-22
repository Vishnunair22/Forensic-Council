import math
import struct
import subprocess
import wave
from pathlib import Path

from PIL import Image, ImageDraw

root = Path("/out")
root.mkdir(exist_ok=True)

img = Image.new("RGB", (320, 220), (238, 241, 245))
draw = ImageDraw.Draw(img)
draw.rectangle((35, 35, 160, 150), outline=(20, 90, 180), width=4)
draw.ellipse((185, 45, 280, 140), fill=(220, 80, 80), outline=(30, 30, 30), width=3)
draw.text((45, 170), "Forensic Council E2E", fill=(10, 10, 10))
img.save(root / "e2e_image.jpg", "JPEG", quality=90)

rate = 16000
with wave.open(str(root / "e2e_audio.wav"), "wb") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(rate)
    frames = bytearray()
    for i in range(rate * 2):
        sample = int(0.35 * 32767 * math.sin(2 * math.pi * 440 * i / rate))
        frames += struct.pack("<h", sample)
    wav.writeframes(frames)

subprocess.run(
    [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "testsrc=size=320x240:rate=12:duration=2",
        "-pix_fmt",
        "yuv420p",
        str(root / "e2e_video.mp4"),
    ],
    check=True,
)

for path in sorted(root.iterdir()):
    if path.is_file() and path.name != "make_fixtures.py":
        print(f"{path.name}\t{path.stat().st_size}")
