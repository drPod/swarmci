"""Deadline + conservative spend cutoff. Standard library so it can run on a model host.
Usage: python budget_watchdog.py CONFIG_JSON
CONFIG contains API key and project instance IDs; keep it mode 0600.
"""

import datetime
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

cfg_path = Path(sys.argv[1])
while True:
    cfg = json.loads(cfg_path.read_text())
    now = time.time()
    deadline = datetime.datetime.fromisoformat(cfg["deadline"]).timestamp()
    spend = cfg.get("initial_spend", 0) + sum(
        max(0, now - i["started"]) / 3600 * i["hourly"] for i in cfg["instances"]
    )
    if now >= deadline or spend >= cfg["cutoff_dollars"]:
        req = urllib.request.Request(
            "https://cloud.lambda.ai/api/v1/instance-operations/terminate",
            data=json.dumps({"instance_ids": [i["id"] for i in cfg["instances"]]}).encode(),
            headers={"Authorization": "Bearer " + cfg["api_key"], "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                print("Fleet termination accepted", response.status, flush=True)
            break
        except (urllib.error.URLError, TimeoutError) as e:
            print("Termination retry:", str(e), flush=True)
            time.sleep(15)
            continue
    time.sleep(20)
