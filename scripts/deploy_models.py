"""Install the two model servers and connect local inference ports. Never prints credentials."""

import asyncio
import json
import secrets
import sys
import time
from pathlib import Path

import httpx
from dotenv import set_key

from swarmci.config import settings

SSH = [
    "ssh",
    "-i",
    ".secrets/lambda_swarmci",
    "-o",
    "StrictHostKeyChecking=accept-new",
    "-o",
    "ConnectTimeout=6",
]
SCP = [
    "scp",
    "-i",
    ".secrets/lambda_swarmci",
    "-o",
    "StrictHostKeyChecking=accept-new",
    "-o",
    "ConnectTimeout=6",
]


async def command(args, check=True):
    p = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await p.communicate()
    if check and p.returncode:
        raise RuntimeError((out + err).decode()[-1200:])
    return p.returncode, (out + err).decode()


async def deploy(item, token):
    role = item["role"]
    deadline = time.monotonic() + 900
    ip = None
    async with httpx.AsyncClient(timeout=15) as c:
        while time.monotonic() < deadline:
            r = await c.get(
                "https://cloud.lambda.ai/api/v1/instances/" + item["id"],
                headers={"Authorization": "Bearer " + settings.lambda_api_key},
            )
            r.raise_for_status()
            info = r.json()["data"]
            ip = info.get("ip")
            if ip:
                code, _ = await command(SSH + ["ubuntu@" + ip, "true"], check=False)
                if code == 0:
                    break
            print(role, "waiting for SSH", info["status"], flush=True)
            await asyncio.sleep(10)
        else:
            raise RuntimeError(role + " SSH boot timeout")
    env_path = Path(".secrets") / (role + ".env")
    env_path.write_text("MODEL_API_KEY=" + token + "\n")
    env_path.chmod(0o600)
    await command(SCP + ["scripts/bootstrap_model.sh", "ubuntu@" + ip + ":swarmci-bootstrap.sh"])
    await command(SCP + [str(env_path), "ubuntu@" + ip + ":swarmci-model.env"])
    await command(
        SSH
        + [
            "ubuntu@" + ip,
            "chmod 600 ~/swarmci-model.env; nohup bash ~/swarmci-bootstrap.sh "
            + role
            + " ~/swarmci-model.env > ~/swarmci-model.log 2>&1 < /dev/null &",
        ]
    )
    port = 8001 if role == "bu" else (8002 if role == "gemma" else 8010 + int(role.split("-")[1]))
    await command(
        SSH
        + [
            "-fNT",
            "-o",
            "ExitOnForwardFailure=yes",
            "-o",
            "ServerAliveInterval=30",
            "-L",
            f"127.0.0.1:{port}:127.0.0.1:8000",
            "ubuntu@" + ip,
        ]
    )
    print(role, "bootstrap started; local tunnel at", port, "host", ip, flush=True)
    async with httpx.AsyncClient(timeout=3) as c:
        while time.monotonic() < deadline:
            try:
                r = await c.get(
                    f"http://127.0.0.1:{port}/v1/models", headers={"Authorization": "Bearer " + token}
                )
                if r.is_success:
                    print(role, "MODEL READY", flush=True)
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(10)
    raise RuntimeError(role + " readiness timeout; inspect ~/swarmci-model.log")


async def main():
    state = json.loads(Path(".secrets/lambda-deployment.json").read_text())
    keys = {}
    for role in ["bu", "gemma"]:
        p = Path(".secrets") / (role + ".env")
        token = p.read_text().strip().split("=", 1)[1] if p.exists() else secrets.token_urlsafe(32)
        keys[role] = token
        p.write_text("MODEL_API_KEY=" + token + "\n")
        p.chmod(0o600)
        set_key(".env", role.upper() + "_API_KEY", token)
    set_key(".env", "GEMMA_MODEL", "google/gemma-3-4b-it")
    async with asyncio.TaskGroup() as group:
        for item in state["instances"]:
            if "--pool-only" in sys.argv and not item["role"].startswith("gemma-"):
                continue
            group.create_task(deploy(item, keys["bu" if item["role"] == "bu" else "gemma"]))


asyncio.run(main())
