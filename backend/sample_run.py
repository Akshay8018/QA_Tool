import asyncio
import json

import httpx


async def main():
    payload = {
        "instruction": "Validate login flow and verify dashboard appears",
        "target_url": "https://example.com",
        "execution_engine": "api",
        "test_data": {
            "email": "qa@example.com",
            "password": "secret",
            "expected_text": "example",
        },
    }
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        response = await client.post("/v1/tests/run-with-report", json=payload)
        response.raise_for_status()
        print(json.dumps(response.json(), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
