"""Install the existing app and join the Lambda hosts to an existing Ray runtime."""

import asyncio
import json
import tarfile
from pathlib import Path

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


async def command(args):
    p = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await p.communicate()
    if p.returncode:
        raise RuntimeError((out + err).decode()[-1800:])


async def install(item, head):
    ip = item["ip"]
    private = item["private_ip"]
    role = "head" if item["id"] == head["id"] else "worker"
    env = Path(".secrets/worker.env")
    await command(
        SCP + [".secrets/swarmci-code.tar.gz", "scripts/bootstrap_worker.sh", "ubuntu@" + ip + ":."]
    )
    await command(SSH + ["ubuntu@" + ip, "mkdir -p ~/swarmci"])
    await command(SCP + [str(env), "ubuntu@" + ip + ":swarmci/.env"])
    await command(
        SSH
        + [
            "ubuntu@" + ip,
            "chmod 600 ~/swarmci/.env; nohup bash ~/bootstrap_worker.sh "
            + private
            + " "
            + head["private_ip"]
            + " "
            + role
            + " > ~/swarmci-worker.log 2>&1 < /dev/null &",
        ]
    )
    print(item["role"], "Ray worker installation started", flush=True)


async def main():
    state = json.loads(Path(".secrets/lambda-deployment.json").read_text())
    pool = [i for i in state["instances"] if i["role"].startswith("gemma-")]
    head = pool[0]
    with tarfile.open(".secrets/swarmci-code.tar.gz", "w:gz") as tar:
        for name in ["pyproject.toml", "uv.lock", ".python-version", "swarmci", "targets", "infra", "tests"]:
            tar.add(name, filter=lambda item: None if "__pycache__" in item.name else item)
    # Only inference/observability credentials; no cloud infrastructure key in agent environments.
    env = (
        "\n".join(
            [
                "GEMMA_BASE_URL=http://" + head["private_ip"] + ":30000/v1",
                "GEMMA_MODEL=google/gemma-4-E4B-it",
                "GEMMA_API_KEY=" + settings.gemma_api_key,
                "BU_BASE_URL=http://127.0.0.1:8001/v1",
                "BU_API_KEY=" + settings.bu_api_key,
                "RESPAN_API_KEY=" + settings.respan_api_key,
                "RESPAN_ENDPOINT=" + settings.respan_endpoint,
                "FIXTURE_URL=http://" + head["private_ip"] + ":8080/fixture",
                "RAY_ADDRESS=auto",
                "EXECUTION=ray",
                "ANONYMIZED_TELEMETRY=false",
                "RAY_USAGE_STATS_ENABLED=0",
            ]
        )
        + "\n"
    )
    p = Path(".secrets/worker.env")
    p.write_text(env)
    p.chmod(0o600)
    await install(head, head)
    await asyncio.gather(*(install(i, head) for i in pool[1:]))


asyncio.run(main())
