# Deployment

Frontend: https://swarmci.vercel.app
Backend: https://swarmci-api.40-160-241-64.sslip.io

Vercel serves only `swarmci/static` via the build in `vercel.json`. API and artifact requests are forwarded to the VPS through Caddy. `.vercelignore` restricts uploads to frontend assets and deployment configuration.

The backend runs on `myvps` from `/home/coder/Coding/gradient-hackathon`. Its live SQLite database is `/home/coder/.local/share/swarmci/data/swarmci.db`, outside Mutagen to avoid concurrent database synchronization. It was initialized with a consistent backup of the local database. Artifacts remain in the project's `artifacts` directory. Source edits sync with Mutagen; restart the backend to load Python changes.

```sh
ssh myvps 'systemctl --user restart swarmci'
ssh myvps 'journalctl --user -u swarmci -n 100 --no-pager'
vercel deploy --prod --yes
```

Systemd units are recorded in `infra/vps/` and installed in `~/.config/systemd/user/` on the VPS. The backend and BU/Gemma inference tunnels are enabled at boot; user lingering is enabled. The tunnels connect to the existing Lambda instances, with Gemma using the existing router on gemma-1. If those instances are replaced, update the tunnel units. This deployment does not provision model instances or start the separate Plane/Penpot target applications.

Caddy's site is `~/deploy/caddy/sites/swarmci.caddy` on the VPS. Its rootless Docker network reaches the host backend at `40.160.241.64:8080`. Reload changes with:

```sh
ssh myvps 'docker exec caddy caddy validate --config /etc/caddy/Caddyfile && docker exec caddy caddy reload --config /etc/caddy/Caddyfile'
```

Deployment checks: public API health, Browser Use/Gemma connectivity, static dashboard loading in Chromium without JavaScript errors, live SSE delivery, completed two-worker Component Lab exploration (`1355da3afd50`), and access to the Penpot review evidence JSON. The short exploration completed 11 transitions and 5 handoffs without infrastructure errors; it was a deployment smoke check, not a full regression search.

The VPS disk was full and Mutagen had disconnected. Downloadable apt, Yarn, pnpm, and Node caches were cleared and `coding-vps` resumed. Historical artifact transfers were still catching up at deployment time. Existing sync conflicts in `free-autumn/data/person-matching-all/progress-vps.json` and `orchard/.git/index` were left untouched.

Storage safeguards are enabled. `/api/health` reports free space across the database and artifact filesystems. New API explorations are rejected with HTTP 503 below 2 GiB free. A five-second watchdog cancels active explorations and narration below 1 GiB free, retaining existing evidence and leaving the web server running. Thresholds are configurable with `STORAGE_MIN_FREE_BYTES` and `STORAGE_CRITICAL_FREE_BYTES`.

`swarmci-storage.timer` checks disk space every minute. It maintains a physically allocated 256 MiB emergency reserve in `~/.local/share/swarmci/disk-reserve`, releases it below 2.25 GiB free, and recreates it only above 4 GiB free. Current status is in `~/.local/share/swarmci/storage-status.json`; timer output is in the user journal. Its installed script is outside the synced source tree. It does not delete evidence or unrelated project files.

With explicit approval, the old `phase5-artifact-replay` and `phase5-evaluation` bash-spec-pilot cache directories were removed after backing them up to `/Users/darshpoddar/.cache/vps-archives/bash-spec-cache-20260912.tar.gz`. All 6,524 files/symlinks were checked against the live originals, and gzip integrity was validated. Archive SHA-256: `1db2c87db67d21b9da25d90249bf8b9dc91798363ba3c0efc0114a35b7480066`. The adjacent `.verified.json` contains the file manifest. Reconstruct the directories by extracting the archive under `/home/coder/.cache/bash-spec-pilot`.

These safeguards limit this application's disk consumption under pressure; unrelated processes and Mutagen can still consume the shared filesystem. Sustained growth requires additional capacity or reviewed cleanup. No automatic evidence-retention deletion is enabled.
