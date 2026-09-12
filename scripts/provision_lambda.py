"""Provision only the explicitly selected hackathon model hosts, reusing recorded IDs."""

import asyncio
import json
from pathlib import Path

import httpx

from swarmci.config import settings


async def main():
    state_file = Path(".secrets/lambda-deployment.json")
    state = json.loads(state_file.read_text()) if state_file.exists() else {"instances": []}
    async with httpx.AsyncClient(timeout=40) as client:
        headers = {"Authorization": "Bearer " + settings.lambda_api_key}
        if not state.get("ssh_key"):
            r = await client.post(
                "https://cloud.lambda.ai/api/v1/ssh-keys",
                headers=headers,
                json={
                    "name": "swarmci-hackathon",
                    "public_key": Path(".secrets/lambda_swarmci.pub").read_text().strip(),
                },
            )
            r.raise_for_status()
            state["ssh_key"] = r.json()["data"]["name"]
            state_file.write_text(json.dumps(state, indent=2))
        for role, kind, region in [
            ("bu", "gpu_1x_h100_pcie", "us-west-3"),
            ("gemma", "gpu_1x_a10", "us-west-1"),
        ]:
            if any(i["role"] == role for i in state["instances"]):
                continue
            await asyncio.sleep(13)
            r = await client.post(
                "https://cloud.lambda.ai/api/v1/instance-operations/launch",
                headers=headers,
                json={
                    "region_name": region,
                    "instance_type_name": kind,
                    "ssh_key_names": [state["ssh_key"]],
                    "name": "swarmci-" + role,
                    "quantity": 1,
                },
            )
            if not r.is_success:
                print(role, "launch failed", r.status_code, r.text)
                return
            id = r.json()["data"]["instance_ids"][0]
            state["instances"].append({"role": role, "id": id, "type": kind, "region": region})
            state_file.write_text(json.dumps(state, indent=2))
            state_file.chmod(0o600)
            print(role, id, flush=True)


asyncio.run(main())
