import os

import httpx
from dotenv import load_dotenv

load_dotenv()

async def test_groq():
    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        print("Error: LLM_API_KEY is not set in .env")
        return False

    print(f"Testing Groq API key (starts with: {api_key[:10]}...)")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {api_key}"}
            )

            if response.status_code == 200:
                print("✅ Groq API Key is VALID.")
                models = response.json().get("data", [])
                print(f"Found {len(models)} models available.")
                return True
            else:
                print(f"❌ Groq API Key is INVALID. Status: {response.status_code}")
                print(f"Response: {response.text}")
                return False
        except Exception as e:
            print(f"❌ Connection error: {e}")
            return False

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_groq())
