"""Send a real three-worker fixture run to Respan, without model/cloud credentials.

Run: uv run python scripts/respan_smoke.py
Then: bunx --bun @respan/cli@0.14.1 traces list --limit 5
"""

import asyncio
import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from swarmci.adapters.tracing import initialize, shutdown
from swarmci.config import settings
from swarmci.models import RunConfig, Target
from swarmci.runner import Coordinator
from swarmci.store import Store


async def main():
    if initialize() is None:
        raise SystemExit("Configure RESPAN_API_KEY and enable Respan before running this check")

    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    handler = partial(QuietHandler, directory=str(Path("swarmci/static").resolve()))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        target = Target.model_validate_json(Path("targets/fixture.json").read_text())
        target.url = f"http://127.0.0.1:{server.server_port}/fixture.html"
        target.name = "Respan validation — shared browser exploration"
        config = RunConfig(target=target, engine="fixture", workers=3, max_jobs=25, budget_seconds=90)
        store = Store(settings.data_dir / "respan-smoke.db")
        coordinator = Coordinator(store)
        run = store.create_run(config)
        await coordinator.run(run, config)
        result = store.snapshot(run)
        assert result["status"] == "completed", result["status"]
        assert result["metrics"]["verified_bugs"] == 1, result["metrics"]
        assert result["metrics"]["handoffs"] > 0, result["metrics"]
        print(json.dumps({"run_id": run, "status": result["status"], **result["metrics"]}, indent=2))
        store.db.close()
    finally:
        server.shutdown()
        thread.join()
        shutdown()


if __name__ == "__main__":
    asyncio.run(main())
