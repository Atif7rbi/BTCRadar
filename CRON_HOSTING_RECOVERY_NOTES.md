# BTCRadar Cron Hosting Recovery Notes

## What changed

BTCRadar is now separated into two responsibilities:

- **Cron / CLI worker** owns Coinalyze heavy refresh.
- **Flask / Passenger** reads SQLite, serves Dashboard/Analytics, and does only fast price overlay.

Flask no longer starts the Coinalyze collector thread. This avoids Passenger daemon-thread failures.

## New cron entry point

```bash
scripts/refresh_coinalyze.py
```

This script:

1. Loads config and `.env`.
2. Opens the project SQLite DB.
3. Runs one Coinalyze refresh.
4. Builds heavy dashboard snapshots.
5. Writes job status to SQLite.
6. Exits.

Suggested cPanel Cron command:

```bash
/home/sewaellf/virtualenv/public_html/Sniper/btcradar/3.11/bin/python /home/sewaellf/public_html/Sniper/btcradar/scripts/refresh_coinalyze.py >> /home/sewaellf/public_html/Sniper/btcradar/logs/cron_coinalyze.log 2>&1
```

Schedule:

```text
*/15 * * * *
```

## Flask behavior

- `/api/state` does not call Coinalyze.
- `/api/state` loads latest saved snapshots from SQLite and overlays fast prices.
- `/api/coinalyze/refresh` is disabled for actual refresh and returns latest Cron status.
- `/api/jobs/status` returns recent Cron/job runs.

## Important

Do not rely on Passenger background threads for Coinalyze.

Keep `.env` and `data/btc_radar.db` on the server. Do not overwrite them during upload.
