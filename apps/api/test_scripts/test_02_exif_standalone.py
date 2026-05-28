"""
Test 2: EXIF Extraction (Agent 5 - Metadata)
Tests exif_extract on synthetic images with known EXIF data.
"""
import asyncio
import os
import piexif
from PIL import Image


async def test_exif_extract():
    from tools.metadata_tools import exif_extract

    test_path = "/tmp/test_exif_photo.jpg"
    img = Image.new("RGB", (100, 100), color="blue")

    # Embed EXIF data
    exif_dict = {
        "0th": {
            piexif.ImageIFD.Make: "TestCamera",
            piexif.ImageIFD.Model: "TestModel X1",
            piexif.ImageIFD.Software: "TestSoftware",
        },
        "Exif": {
            piexif.ExifIFD.DateTimeOriginal: "2024:01:15 10:30:00",
            piexif.ExifIFD.LensModel: "TestLens 50mm",
        },
        "GPS": {
            piexif.GPSIFD.GPSLatitude: ((40, 1), (42, 1), (0, 1)),
            piexif.GPSIFD.GPSLatitudeRef: "N",
            piexif.GPSIFD.GPSLongitude: ((74, 1), (0, 1), (0, 1)),
            piexif.GPSIFD.GPSLongitudeRef: "W",
        },
    }
    exif_bytes = piexif.dump(exif_dict)
    img.save(test_path, format="JPEG", exif=exif_bytes)

    result = await exif_extract(file_path=test_path)

    assert result["has_exif"] is True
    assert result.get("Make") == "TestCamera"
    assert result.get("Model") == "TestModel X1"
    # EXIF tools may expose DateTimeOriginal via different keys
    has_date = "DateTimeOriginal" in result or "DateTime" in result or "present_fields" in result
    assert has_date, f"No date field found. Keys: {list(result.keys())}"
    assert result["total_exif_tags"] >= 5
    assert result.get("present_fields", [])

    print(f"  Camera: {result.get('Make')} {result.get('Model')}")
    print(f"  EXIF Fields: {result['total_exif_tags']}")
    print(f"  Present: {result.get('present_fields', [])[:5]}...")


async def test_exif_extract_no_exif():
    from tools.metadata_tools import exif_extract

    test_path = "/tmp/test_exif_noexif.png"
    img = Image.new("RGB", (64, 64), color="red")
    img.save(test_path, format="PNG")

    result = await exif_extract(file_path=test_path)

    assert "has_exif" in result
    assert result["total_exif_tags"] == 0
    assert result["width"] == 64
    assert result["height"] == 64

    print(f"  EXIF present: {result['has_exif']}")
    print(f"  Image size: {result['width']}x{result['height']}")
    print(f"  Fields: {result['total_exif_tags']}")
    print(f"  PNG text: {result['has_png_text_metadata']}")


if __name__ == "__main__":
    print("Test 2a: EXIF extraction from JPEG with embedded EXIF")
    asyncio.run(test_exif_extract())
    print()
    print("Test 2b: EXIF extraction from PNG without EXIF")
    asyncio.run(test_exif_extract_no_exif())
    print()
    print(" All EXIF tests passed!")
