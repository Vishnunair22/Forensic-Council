import asyncio
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
import traceback

def get_exif(image_path):
    print(f"Opening {image_path}")
    try:
        image = Image.open(image_path)
        print("Image opened")
        
        from tools.metadata_tools import _get_exif_data
        print("Imported _get_exif_data")
        
        result = _get_exif_data(image)
        print("RESULT:")
        print(result)
        
    except Exception as e:
        print("ERROR:", e)
        traceback.print_exc()

if __name__ == "__main__":
    get_exif("../tests/test_images/test_image.jpg")
