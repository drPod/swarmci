import asyncio
import json
import time
from pathlib import Path

import httpx

from swarmci.config import settings

SSH = [
    "ssh",
    "-i",
    ".secrets/lambda_swarmci",
    "-o",
    "StrictHostKeyChecking=accept-new",
    "-o",
    "ConnectTimeout=5",
]
SCP = [
    "scp",
    "-i",
    ".secrets/lambda_swarmci",
    "-o",
    "StrictHostKeyChecking=accept-new",
    "-o",
    "ConnectTimeout=5",
]


async def command(args, check=True):
    p = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await p.communicate()
    if check and p.returncode:
        raise RuntimeError((out + err).decode()[-1500:])
    return p.returncode


async def deploy(item):
    deadline = time.monotonic() + 900
    async with httpx.AsyncClient(timeout=15) as c:
        while time.monotonic() < deadline:
            r = await c.get(
                "https://cloud.lambda.ai/api/v1/instances/" + item["id"],
                headers={"Authorization": "Bearer " + settings.lambda_api_key},
            )
            r.raise_for_status()
            info = r.json()["data"]
            ip = info.get("ip")
            if ip and await command(SSH + ["ubuntu@" + ip, "true"], False) == 0:
                break
            await asyncio.sleep(10)
        else:
            raise RuntimeError(item["role"] + " boot timeout")
    private = info["private_ip"]
    await command(SCP + ["scripts/bootstrap_sglang.sh", "ubuntu@" + ip + ":swarmci-sglang.sh"])
    await command(SCP + [".secrets/gemma.env", "ubuntu@" + ip + ":swarmci-model.env"])
    await command(
        SSH
        + [
            "ubuntu@" + ip,
            "chmod 600 ~/swarmci-model.env; nohup bash ~/swarmci-sglang.sh "
            + private
            + " ~/swarmci-model.env > ~/swarmci-sglang.log 2>&1 < /dev/null &",
        ]
    )
    print(item["role"], "SGLang bootstrap started", ip, private, flush=True)
    return {**item, "ip": ip, "private_ip": private}


async def main():
    p = Path(".secrets/lambda-deployment.json")
    state = json.loads(p.read_text())
    hosts = await asyncio.gather(*(deploy(i) for i in state["instances"] if i["role"].startswith("gemma-")))
    mapping = {i["id"]: i for i in hosts}
    state["instances"] = [mapping.get(i["id"], i) for i in state["instances"]]
    p.write_text(json.dumps(state, indent=2))


asyncio.run(main())
