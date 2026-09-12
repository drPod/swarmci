"""Print host state, or start SSH tunnels to provisioned model servers."""

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import httpx

from swarmci.config import settings


async def main():
    path = Path(".secrets/lambda-deployment.json")
    state = json.loads(path.read_text())
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            "https://cloud.lambda.ai/api/v1/instances",
            headers={"Authorization": "Bearer " + settings.lambda_api_key},
        )
        r.raise_for_status()
    hosts = {i["id"]: i for i in r.json()["data"]}
    for item in state["instances"]:
        host = hosts.get(item["id"], {})
        print(item["role"], item["id"], host.get("status", "missing"), host.get("ip", "pending"))
        if host.get("ip"):
            item["ip"] = host["ip"]
            if "--tunnel" in sys.argv:
                role = item["role"]
                port = 8001 if role == "bu" else (8002 if role == "gemma" else 8010 + int(role.split("-")[1]))
                subprocess.run(
                    [
                        "ssh",
                        "-fNT",
                        "-i",
                        ".secrets/lambda_swarmci",
                        "-o",
                        "StrictHostKeyChecking=accept-new",
                        "-o",
                        "ExitOnForwardFailure=yes",
                        "-o",
                        "ServerAliveInterval=30",
                        "-L",
                        f"127.0.0.1:{port}:127.0.0.1:8000",
                        "ubuntu@" + item["ip"],
                    ],
                    check=True,
                )
    path.write_text(json.dumps(state, indent=2))


asyncio.run(main())
