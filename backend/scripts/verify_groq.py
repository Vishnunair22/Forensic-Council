import os
import httpx
from dotenv import load_dotenv

load_dotenv()

def test_groq():
    key = os.getenv("LLM_API_KEY")
    if not key:
        return "ERROR: KEY NOT FOUND"
    
    with httpx.Client() as client:
        try:
            r = client.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {key}"}
            )
            return f"STATUS: {r.status_code}"
        except Exception as e:
            return f"EXCEPTION: {str(e)}"

if __name__ == "__main__":
    print(test_groq())
