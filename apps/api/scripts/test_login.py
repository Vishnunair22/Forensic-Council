import asyncio

import httpx


async def test():
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        # Try login with bootstrap password from .env
        r = await client.post(
            "/api/v1/auth/login",
            data={"username": "investigator", "password": "p0HYzcehYwF0zMc1ddH1o9TjU8I5Fe8Y"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        print(f"Login: {r.status_code}")
        if r.status_code == 200:
            print("Got token")
        else:
            print(f"Error: {r.text[:300]}")

asyncio.run(test())
