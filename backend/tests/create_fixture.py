#!/usr/bin/env python
"""Create test fixtures for integration tests."""

import os
import sys

# Change to backend directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from PIL import Image, ImageDraw
import piexif


def create_test_image():
    """Create a test JPEG with splice and EXIF anomalies."""
    # Create fixtures directory
    fixtures_dir = "tests/fixtures"
    os.makedirs(fixtures_dir, exist_ok=True)
    
    # Create base image
    img = Image.new('RGB', (800, 600), color=(200, 200, 200))
    draw = ImageDraw.Draw(img)
    
    # Add shapes
    draw.rectangle([100, 100, 300, 300], fill=(255, 0, 0))
    draw.ellipse([400, 200, 600, 400], fill=(0, 255, 0))
    
    # Create splice in upper-left quadrant
    upper_left = img.crop((400, 300, 600, 500))
    img.paste(upper_left, (50, 50))
    
    # Create EXIF data with stripped software field
    exif_dict = {
        '0th': {},
        'Exif': {},
        'GPS': {},
        '1st': {},
        'thumbnail': None,
    }
    
    exif_bytes = piexif.dump(exif_dict)
    
    # Save to fixtures
    output_path = os.path.join(fixtures_dir, 'test_spliced_image.jpg')
    img.save(output_path, format='JPEG', exif=exif_bytes, quality=95)
    print(f'Created {output_path}')


if __name__ == "__main__":
    create_test_image()
