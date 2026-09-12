"""Maintain a small emergency disk reserve; never delete application evidence."""

import json
import os
import shutil
from pathlib import Path

GIB = 1024**3
RESERVE_BYTES = 256 * 1024**2
ROOT = Path.home() / ".local/share/swarmci"
RESERVE = ROOT / "disk-reserve"


def maintain(root=ROOT, reserve=RESERVE):
    root.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(root).free
    action = "none"
    if free < 2 * GIB + RESERVE_BYTES and reserve.exists():
        reserve.unlink()
        action = "released emergency reserve"
    elif free > 4 * GIB and not reserve.exists():
        # fallocate allocates real blocks; truncate alone would create a sparse file.
        try:
            with reserve.open("xb") as f:
                os.posix_fallocate(f.fileno(), 0, RESERVE_BYTES)
                os.fsync(f.fileno())
            action = "allocated emergency reserve"
        except OSError:
            reserve.unlink(missing_ok=True)
            raise
    free = shutil.disk_usage(root).free
    status = {"free_bytes": free, "reserve_bytes": reserve.stat().st_size if reserve.exists() else 0,
              "low_space": free < 3 * GIB, "action": action}
    temporary = root / "storage-status.tmp"
    temporary.write_text(json.dumps(status) + "\n")
    temporary.replace(root / "storage-status.json")
    print(json.dumps(status))


if __name__ == "__main__":
    maintain()
