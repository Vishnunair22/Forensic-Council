import os
import httpx
from dotenv import load_dotenv

load_dotenv()

def test_gemini():
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        return "ERROR: GEMINI_API_KEY NOT FOUND"
    
    # Use the v1beta models endpoint to list models
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
    
    with httpx.Client() as client:
        try:
            r = client.get(url)
            if r.status_code == 200:
                models = r.json().get("models", [])
                return f"STATUS: 200 OK (Found {len(models)} models)"
            else:
                return f"STATUS: {r.status_code} - {r.text}"
        except Exception as e:
            return f"EXCEPTION: {str(e)}"

if __name__ == "__main__":
    print(test_gemini())
