"""Start the pinned real Plane app and private fixture broker using existing Docker Compose."""

import argparse
import secrets
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from swarmci.plane_service import COMPOSE  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("command", choices=["up", "down", "status", "broker"], default="up", nargs="?")
args = parser.parse_args()
(ROOT / "data").mkdir(exist_ok=True)
(ROOT / ".secrets").mkdir(exist_ok=True)
token = ROOT / ".secrets/plane-fixtures-token"
if not token.exists():
    token.write_text(secrets.token_urlsafe(32))
    token.chmod(0o600)
env = ROOT / "data/plane.env"
if not env.exists():
    env.write_text(
        "APP_RELEASE=v1.2.3\nAPP_DOMAIN=localhost\nWEB_URL=http://localhost:8090\n"
        "CORS_ALLOWED_ORIGINS=http://localhost:8090,http://127.0.0.1:8090\nLISTEN_HTTP_PORT=8090\n"
        "LISTEN_HTTPS_PORT=8444\nSITE_ADDRESS=:80\nSECRET_KEY="
        + secrets.token_hex(32)
        + "\nCERT_EMAIL=\nCERT_ACME_CA=https://acme-v02.api.letsencrypt.org/directory\nCERT_ACME_DNS=\n"
    )
    env.chmod(0o600)
if args.command == "broker":
    import uvicorn

    uvicorn.run("swarmci.plane_service:app", host="127.0.0.1", port=8091)
elif args.command == "status":
    subprocess.run(COMPOSE + ["ps"], check=True)
elif args.command == "down":
    subprocess.run(COMPOSE + ["down"], check=True)
else:
    subprocess.run(COMPOSE + ["up", "-d"], check=True)
    for attempt in range(120):
        try:
            if httpx.get("http://localhost:8090/api/instances/", timeout=3).is_success:
                print(
                    "Plane ready: http://localhost:8090\nStart broker: uv run python scripts/plane_local.py broker"
                )
                break
        except httpx.HTTPError:
            pass
        time.sleep(2)
    else:
        raise SystemExit("Plane did not become ready; inspect Docker Compose logs")
