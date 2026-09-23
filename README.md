# Cotton On-Call

Tracks the CFTC weekly Cotton On-Call (COC) report: unfixed-price call cotton
sales and purchases, and open ICE futures interest, by contract month.

- Source: https://www.cftc.gov/MarketReports/CottonOnCall/HistoricalCottonOn-Call/index.htm
- Release: Thursdays ~3:30pm ET, data as-of the previous Friday (may be delayed by federal holidays).

## Folders

- `Database/` — `Old Database.csv` is the legacy history (2004 onward, one-off pull).
  `Cotton_On_Call_Database.csv` is the live master, long format:
  `Date, Fut, Tag, Value, month, year` where `Tag` is one of
  `Sales, S Change, Purchase, P Change, OI, OI Change` (per futures contract month,
  plus a `Totals` row).
- `Code/ingest_coc.py` — scrapes the CFTC index page, parses any report newer
  than what's already in the master database, and appends it. Idempotent —
  safe to re-run; re-releases of an already-ingested week are skipped.
  Run `python ingest_coc.py --rebuild` to rebuild the master entirely from
  `Old Database.csv` plus a full site history scrape.
- `Automator/run_coc_update.bat` + `setup_task.ps1` — weekly Task Scheduler job
  (Fridays 8:00 AM) that runs the ingest script and logs to `coc_update.log`.
- `Dashboard/` — not yet built.

## Next steps

- Dashboard visualizing Sales/Purchases/OI history by contract month.
- Link with CT Rollex price history for a Thursday-to-Thursday on-call
  change vs. price change model (per Romain).
