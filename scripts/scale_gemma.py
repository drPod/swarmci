"""Add the eight explicitly requested Gemma hosts; preserve each recorded role."""

import asyncio
import json
from pathlib import Path

import httpx

from swarmci.config import settings


async def main():
    path = Path(".secrets/lambda-deployment.json")
    state = json.loads(path.read_text())
    existing = {i["role"] for i in state["instances"]}
    roles = [f"gemma-{i}" for i in range(1, 9) if f"gemma-{i}" not in existing]
    if not roles:
        print("All eight Gemma scale-out hosts already recorded")
        return
    async with httpx.AsyncClient(timeout=40) as c:
        for role in roles:
            await asyncio.sleep(13)
            r = await c.post(
                "https://cloud.lambda.ai/api/v1/instance-operations/launch",
                headers={"Authorization": "Bearer " + settings.lambda_api_key},
                json={
                    "region_name": "us-west-2",
                    "instance_type_name": "gpu_1x_a100_sxm4",
                    "ssh_key_names": [state["ssh_key"]],
                    "name": "swarmci-" + role,
                    "quantity": 1,
                },
            )
            if not r.is_success:
                print(role, "launch failed:", r.status_code, r.text, flush=True)
                continue
            id = r.json()["data"]["instance_ids"][0]
            state["instances"].append(
                {"role": role, "id": id, "type": "gpu_1x_a100_sxm4", "region": "us-west-2"}
            )
            path.write_text(json.dumps(state, indent=2))
            print(role, id, flush=True)


asyncio.run(main())
