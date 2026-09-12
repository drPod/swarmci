"""Disk headroom checks for the coordinator's data and browser evidence."""

import asyncio
import logging
import shutil

from swarmci.config import settings

GIB = 1024**3
logger = logging.getLogger(__name__)


def storage_status():
    paths = (settings.data_dir, settings.artifact_dir)
    free = min(shutil.disk_usage(path).free for path in paths)
    return {
        "free_bytes": free,
        "minimum_free_bytes": settings.storage_min_free_bytes,
        "critical_free_bytes": settings.storage_critical_free_bytes,
        "accepting_runs": free >= settings.storage_min_free_bytes,
    }


def cancel_if_critical(coordinator, narration):
    status = storage_status()
    if status["free_bytes"] >= settings.storage_critical_free_bytes:
        return
    for run, task in list(coordinator.tasks.items()):
        if not task.done() and not task.cancelling():
            logger.warning("Cancelling run %s: critically low disk space", run)
            coordinator.store.event(run, "storage.low", {
                "message": "Exploration stopped to preserve disk space. Free storage before restarting.",
                "free_bytes": status["free_bytes"],
            })
            task.cancel()
    for task in list(narration.tasks.values()):
        if not task.done() and not task.cancelling():
            task.cancel()


async def watch_storage(coordinator, narration):
    while True:
        try:
            cancel_if_critical(coordinator, narration)
        except OSError:
            logger.exception("Unable to check disk space")
        await asyncio.sleep(5)
