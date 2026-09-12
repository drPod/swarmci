"""Register healthy replicas using SGLang Model Gateway's existing worker API."""

import asyncio
import json
import time
from pathlib import Path

import httpx

from swarmci.config import settings


async def main():
    pool = [
        i
        for i in json.loads(Path("fleet-hosts.json").read_text())["instances"]
        if i["role"].startswith("gemma-")
    ]
    pending = {i["role"]: i for i in pool}
    deadline = time.monotonic() + 1200
    headers = {"Authorization": "Bearer " + settings.gemma_api_key}
    async with httpx.AsyncClient(timeout=4) as c:
        while pending and time.monotonic() < deadline:
            for role, item in list(pending.items()):
                url = "http://" + item["private_ip"] + ":8000"
                try:
                    health = await c.get(url + "/health", headers=headers)
                    if health.is_success:
                        r = await c.post(
                            settings.gemma_base_url.removesuffix("/v1") + "/workers",
                            headers=headers,
                            json={"url": url, "api_key": settings.gemma_api_key},
                        )
                        if r.is_success:
                            print(role, "registered with cache-aware gateway", flush=True)
                            del pending[role]
                        else:
                            print(role, "gateway registration HTTP", r.status_code, flush=True)
                except httpx.HTTPError:
                    pass
            if pending:
                print("Waiting for models:", ",".join(pending), flush=True)
                await asyncio.sleep(10)
    if pending:
        raise RuntimeError("Model readiness deadline exceeded")


asyncio.run(main())
