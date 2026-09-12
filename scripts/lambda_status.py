"""Read-only readiness check. Deliberately does not provision billable instances."""

import asyncio

import httpx

from swarmci.config import settings


async def main():
    if not settings.lambda_api_key:
        raise SystemExit("Set LAMBDA_API_KEY in .env")
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            "https://cloud.lambda.ai/api/v1/instances",
            headers={"Authorization": "Bearer " + settings.lambda_api_key},
        )
        r.raise_for_status()
        for item in r.json()["data"]:
            print(item["id"], item["status"], item.get("ip", "pending"))
        if not r.json()["data"]:
            print("No running instances. Local build is ready; deployment is deferred.")


asyncio.run(main())
