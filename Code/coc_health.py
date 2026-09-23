"""
Shared master-database helpers for Cotton On-Call: paths, loading, and the
data-health check. Pandas-only (no requests/bs4) so it can be imported by
the Streamlit dashboard without pulling in scraper dependencies.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_DIR = REPO_ROOT / "Database"
OLD_CSV = DB_DIR / "Old Database.csv"
MASTER_CSV = DB_DIR / "Cotton_On_Call_Database.csv"

# Live source, only reachable from the desk machine (Rollex pipeline refreshes it daily).
ROLLEX_CT_LIVE_PATH = Path(
    r"C:\Users\virat.arya\ETG\SoftsDatabase - Documents\Database\Hardmine\LSEG\Rollex\Database\rollex_CT.parquet"
)
# Full copy (all columns, full history) shipped in the repo so the Price Link tab also
# works on Streamlit Cloud, which can't see the desk machine's filesystem, and so the
# repo carries its own copy of the price history it depends on. Refreshed by the Automator
# and pushed to GitHub alongside the master database.
ROLLEX_CT_SNAPSHOT = DB_DIR / "rollex_CT.parquet"


def refresh_rollex_ct_snapshot() -> bool:
    """Copy the full live Rollex CT parquet (all columns, full history) into the repo.
    Returns True if refreshed, False if the live source isn't reachable (e.g. off the
    desk machine) - in that case the existing snapshot, if any, is left untouched."""
    if not ROLLEX_CT_LIVE_PATH.exists():
        return False
    DB_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROLLEX_CT_LIVE_PATH, ROLLEX_CT_SNAPSHOT)
    return True

COLUMNS = ["Date", "Fut", "Tag", "Value", "month", "year"]
TAG_FIXUPS = {"S change": "S Change"}


def load_master() -> pd.DataFrame:
    if MASTER_CSV.exists():
        df = pd.read_csv(MASTER_CSV, parse_dates=False)
    elif OLD_CSV.exists():
        df = pd.read_csv(OLD_CSV, parse_dates=False)[COLUMNS]
    else:
        return pd.DataFrame(columns=COLUMNS)
    df["Tag"] = df["Tag"].replace(TAG_FIXUPS)
    # legacy rows in Old Database.csv have thousands-separator commas baked into Value as text
    df["Value"] = pd.to_numeric(df["Value"].astype(str).str.replace(",", "", regex=False), errors="coerce").fillna(0).astype(int)
    return df


def latest_date(df: pd.DataFrame):
    if df.empty:
        return None
    return pd.to_datetime(df["Date"], format="%m/%d/%Y").max().date()


def health_check(df: pd.DataFrame) -> list[str]:
    """Return a list of human-readable data-quality issues, empty if clean."""
    issues = []
    if df.empty:
        return ["Master database is empty."]

    dates = sorted(pd.to_datetime(df["Date"].unique(), format="%m/%d/%Y"))
    last = dates[-1].date()
    stale_days = (datetime.today().date() - last).days
    if stale_days > 10:
        issues.append(f"Latest as-of date is {last} - {stale_days} days old (report is weekly, expect <=10).")

    gaps = []
    for prev, cur in zip(dates, dates[1:]):
        gap = (cur - prev).days
        if gap > 10:
            gaps.append(f"{prev.date()} -> {cur.date()} ({gap}d)")
    if gaps:
        issues.append(f"{len(gaps)} gap(s) wider than 10 days: " + "; ".join(gaps[:5]) + (" ..." if len(gaps) > 5 else ""))

    dupes = df.duplicated(subset=["Date", "Fut", "Tag"]).sum()
    if dupes:
        issues.append(f"{dupes} duplicate (Date, Fut, Tag) row(s).")

    non_numeric = pd.to_numeric(df["Value"].astype(str).str.replace(",", "", regex=False), errors="coerce").isna().sum()
    if non_numeric:
        issues.append(f"{non_numeric} row(s) with non-numeric Value.")

    dates_with_totals = set(pd.to_datetime(df.loc[df["Fut"] == "Totals", "Date"], format="%m/%d/%Y"))
    missing_totals = [d.date() for d in dates if d not in dates_with_totals]
    if missing_totals:
        issues.append(f"{len(missing_totals)} report date(s) missing a Totals row: {missing_totals[:5]}")

    return issues
