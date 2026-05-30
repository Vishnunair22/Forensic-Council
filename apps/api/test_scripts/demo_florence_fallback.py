import asyncio
import os
import sys
from PIL import Image, ImageDraw

# Add apps/api to path
sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from core.gemini_client import GeminiVisionClient, GeminiVisionFinding
from core.config import Settings


def create_test_image(path: str):
    """Create a simple test image with a red box and a blue circle on yellow background."""
    img = Image.new("RGB", (400, 400), color=(255, 255, 200)) # pale yellow
    draw = ImageDraw.Draw(img)
    # Red rectangle
    draw.rectangle([50, 50, 150, 150], fill=(255, 0, 0), outline=(0, 0, 0))
    # Blue circle
    draw.ellipse([200, 200, 300, 300], fill=(0, 0, 255), outline=(0, 0, 0))
    img.save(path)
    print(f"Created test image at {path}")


async def main():
    print("==========================================================")
    print("DEMONSTRATING FLORENCE-2 FORENSIC FALLBACK INTEGRATION")
    print("==========================================================")

    # 1. Setup paths
    test_img_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "fallback_test_image.jpg"))
    create_test_image(test_img_path)

    # 2. Simulate Gemini unavailability by passing empty API key configuration
    print("\n[1] Instantiating Gemini client with Gemini API disabled...")
    settings = Settings(
        app_env="testing",
        signing_key="test-signing-key-" + "x" * 32,
        postgres_user="test",
        postgres_password="test",
        postgres_db="test",
        redis_password="test",
        DEMO_PASSWORD="test",
        llm_provider="none",
        llm_api_key=None,
        llm_model="test-model",
        gemini_api_key=None,  # Disabled
        bootstrap_admin_password="Admin_123!",
        bootstrap_investigator_password="Inv_123!",
    )
    
    client = GeminiVisionClient(settings)
    print(f"    - Client Gemini Enabled: {client._enabled}")

    # 3. Execute fallback pipeline
    print("\n[2] Executing forensic analysis (triggers local ensemble + Florence-2 fallback)...")
    try:
        finding = await client.identify_file_content(test_img_path)
        
        # 4. Display Results
        print("\n==========================================================")
        print("                 FORENSIC REPORT FINDINGS")
        print("==========================================================")
        print(f"Model Used:           {finding.model_used}")
        print(f"Provider Used:        {finding.provider_used}")
        print(f"Confidence score:     {finding.confidence:.2f}")
        print(f"Court Defensible:     {finding.court_defensible}")
        print("\n--- CONTENT DESCRIPTION ---")
        print(finding.content_description)
        print("\n--- CONTEXTUAL NARRATIVE ---")
        print(finding._contextual_narrative)
        print("\n--- INVESTIGATOR CAVEAT ---")
        print(finding.caveat)
        print("\n--- DETECTED OBJECTS ---")
        print(finding.detected_objects)
        print("==========================================================")
        
    except Exception as e:
        print(f"\n[ERROR] Fallback execution failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        if os.path.exists(test_img_path):
            os.remove(test_img_path)
            print("\nRemoved test image.")


if __name__ == "__main__":
    asyncio.run(main())
