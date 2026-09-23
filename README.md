# Cotton On-Call

Tracks the CFTC weekly Cotton On-Call (COC) report: unfixed-price call cotton
sales and purchases, and open ICE futures interest, by contract month.

- Source: https://www.cftc.gov/MarketReports/CottonOnCall/HistoricalCottonOn-Call/index.htm
- Release: Thursdays ~3:30pm ET, data as-of the previous Friday (may be delayed by federal holidays).

## Folders

- `Database/Cotton_On_Call_Database.csv` — the master, long format:
  `Date, Fut, Tag, Value, month, year` where `Tag` is one of
  `Sales, S Change, Purchase, P Change, OI, OI Change` (per futures contract month,
  plus a `Totals` row). Sourced entirely from CFTC's own historical report pages
  (2003-06-20 onward) via `ingest_coc.py --rebuild` — see "Data history" below.
- `Database/Old Database.csv` — the original one-off legacy pull (2004+). Kept only
  as a historical backup; the master database no longer depends on it (CFTC's site
  hosts reports going back further than this file's start date, so a `--rebuild`
  never needs it). Do not open/save this file in Excel — that's what corrupted its
  date/month formatting once already (fixed via git history, see commit e6df494).
- `Database/rollex_CT.parquet` — a full copy (all columns, full history) of the CT
  Rollex price series, refreshed by the Automator from the desk machine's live
  Rollex pipeline (`Hardmine/LSEG/Rollex/Database/rollex_CT.parquet`) and pushed to
  GitHub so the Price Link dashboard tab also works on Streamlit Cloud.
- `Code/coc_health.py` — shared helpers (paths, `load_master()`, `health_check()`,
  `fut_expiry_date()`) with minimal dependencies (pandas only) so the dashboard can
  import it without pulling in scraper-only packages.
- `Code/ingest_coc.py` — the scraper.
  - `python ingest_coc.py` — normal weekly run: parses any report newer than
    what's already in the master, appends it. Idempotent — safe to re-run.
  - `python ingest_coc.py --rebuild` — rebuilds the master entirely by re-scraping
    every report CFTC's site currently hosts (concurrent fetch, ~1300+ reports).
    Only falls back to `Old Database.csv` for dates older than the earliest report
    CFTC still hosts (currently none needed — CFTC's coverage starts 2003-06-20,
    before `Old Database.csv` even begins).
- `Automator/run.bat` + `notify.py` — weekly pipeline: ingest → git push → Outlook
  email summary (mirrors the Rollex automator pattern). Registered in Task
  Scheduler manually as a basic cmd.exe task.
- `Dashboard/coc_dashboard.py` — Streamlit dashboard (`streamlit run coc_dashboard.py`),
  also deployed on Streamlit Community Cloud. Tabs: Totals Over Time, By Contract
  Month (nearest-expiry first), Imbalance Heatmap, Seasonality, Price Link (CT
  Rollex), Expiry Watch (proof of concept), Data Health.

## Data history / known limitations

- CFTC's site has changed its report page HTML structure at least 3 times over
  the report's ~20-year history; `ingest_coc.py`'s parser is markup-agnostic
  (matches rows by content — "Month YYYY" or "Totals" — not by tag/attribute) so
  it survives all of them.
- `Old Database.csv` (the original legacy pull, 2004–2020) was found to have real
  label/value corruption for dates in ~2009–2020: the same contract month label
  (e.g. "December 01") was reused 2–3x per report for different real contract
  years, with values not even reliably in occurrence order. This wasn't fixable
  by relabelling — only by getting the real numbers from CFTC directly, which is
  what `--rebuild` now does. The corrupted legacy file is no longer used for any
  date the live rescrape covers.
- The very earliest reports (roughly Jan–Jun 2003) use a plain-text/`<pre>`-style
  page layout that predates real HTML tables and isn't parsed yet — a known,
  small gap (currently unrecoverable without a separate text-format parser).
- A handful of reports (~24 rows, Dec 2009–Jan 2010, all "July 11") genuinely
  duplicate a contract-month label within a single CFTC report page itself —
  verified directly against the live source, not a scraper artifact. Both values
  are kept (not merged/dropped) and flagged by `health_check()`.

## Next steps

- Possible further dashboard views not yet built: percentile-rank KPI, weekly
  digest table, raw data explorer/CSV export.
- Backtest/tune the Expiry Watch imbalance-vs-OI threshold once there's a view on
  what's actually predictive (currently an unvalidated starting guess).
