"""Run Plane exploration locally or on the existing Ray fleet, with an isolated run database."""

import argparse
import asyncio
import json
import os
from pathlib import Path

from swarmci.adapters.tracing import initialize, shutdown
from swarmci.config import settings
from swarmci.models import RunConfig, Target
from swarmci.runner import Coordinator
from swarmci.store import Store

parser = argparse.ArgumentParser()
parser.add_argument("--workers", type=int, default=3)
parser.add_argument("--jobs", type=int, default=40)
parser.add_argument("--seconds", type=int, default=300)
parser.add_argument("--ray", action="store_true")
args = parser.parse_args()
if args.ray:
    import ray

    import swarmci

    token = os.environ.get("PLANE_FIXTURE_TOKEN") or Path(".secrets/plane-fixtures-token").read_text().strip()
    ray.init(
        address=settings.ray_address,
        namespace="swarm-plane",
        log_to_driver=False,
        runtime_env={
            "py_modules": [swarmci],
            "env_vars": {
                "GEMMA_BASE_URL": settings.gemma_base_url,
                "GEMMA_MODEL": settings.gemma_model,
                "GEMMA_API_KEY": settings.gemma_api_key,
                "BU_BASE_URL": settings.bu_base_url,
                "BU_API_KEY": settings.bu_api_key,
                "RESPAN_API_KEY": settings.respan_api_key,
                "RESPAN_BASE_URL": settings.respan_base_url,
                "PLANE_FIXTURE_URL": "http://127.0.0.1:8092",
                "PLANE_FIXTURE_TOKEN": token,
                "ANONYMIZED_TELEMETRY": "false",
            },
        },
    )
config = RunConfig(
    target=Target.model_validate_json(Path("targets/plane.json").read_text()),
    engine="gemma",
    workers=args.workers,
    max_jobs=args.jobs,
    budget_seconds=args.seconds,
    max_depth=24,
    branch_steps=5,
    use_gemma=True,
    execution="ray" if args.ray else "local",
)
store = Store(settings.data_dir / "swarmci.db")


async def main():
    run = store.create_run(config)
    Path("data/plane-active-run").write_text(run)
    print("Plane run " + run, flush=True)
    await Coordinator(store).run(run, config)
    snapshot = store.snapshot(run)
    output = Path("data/plane-run-result.json")
    output.write_text(json.dumps(snapshot, indent=2))
    print(json.dumps({k: snapshot[k] for k in ("id", "status", "metrics", "jobs")}, indent=2), flush=True)


initialize()
try:
    asyncio.run(main())
finally:
    shutdown()
