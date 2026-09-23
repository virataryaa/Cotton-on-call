"""
Cotton On-Call (COC) ingest pipeline.

Source: CFTC Historical Cotton On-Call reports
  Index : https://www.cftc.gov/MarketReports/CottonOnCall/HistoricalCottonOn-Call/index.htm
  Report: https://www.cftc.gov/MarketReports/CottonOnCall/HistoricalCottonOn-Call/deaoncall{MMDDYY}.html

Reports are released weekly (Thursday, ~3:30pm ET) and carry data "as of" the
previous Friday. This script scrapes the index page for every report link,
skips any report whose as-of date is already in the master database, parses
new reports, and appends them in the same long format as the legacy
"Old Database.csv" (Date, Fut, Tag, Value, month, year).

Usage:
    python ingest_coc.py            # update the master database with new reports
    python ingest_coc.py --rebuild  # rebuild master from Old Database.csv + full history scrape
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE = "https://www.cftc.gov"
INDEX_URL = f"{BASE}/MarketReports/CottonOnCall/HistoricalCottonOn-Call/index.htm"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_DIR = REPO_ROOT / "Database"
OLD_CSV = DB_DIR / "Old Database.csv"
MASTER_CSV = DB_DIR / "Cotton_On_Call_Database.csv"

COLUMNS = ["Date", "Fut", "Tag", "Value", "month", "year"]
TAGS = ["Sales", "S Change", "Purchase", "P Change", "OI", "OI Change"]


def list_reports() -> list[dict]:
    """Scrape the historical index page for every report link + release date."""
    resp = requests.get(INDEX_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    reports = []
    for a in soup.select("a[href*='deaoncall']"):
        href = a["href"]
        url = href if href.startswith("http") else BASE + href
        td = a.find_parent("td")
        release_date = None
        if td:
            for m in re.finditer(r"(\d{2}/\d{2}/\d{4})", td.get_text()):
                try:
                    release_date = datetime.strptime(m.group(1), "%m/%d/%Y").date()
                    break
                except ValueError:
                    continue
        reports.append({"url": url, "label": a.get_text(strip=True), "release_date": release_date})

    reports.sort(key=lambda r: r["release_date"] or datetime.min.date())
    return reports


def _clean_int(text: str) -> int:
    text = text.replace("\xa0", "").replace(",", "").strip()
    if text in ("", "-"):
        return 0
    return int(text)


def parse_report(url: str) -> tuple[datetime.date, list[tuple]]:
    """Parse a single COC report page. Returns (as_of_date, rows).

    Each row is (fut_label, sales, s_change, purchase, p_change, oi, oi_change).
    """
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    m = re.search(r"as of\s+(\d{2}/\d{2}/\d{4})", soup.get_text())
    if not m:
        raise ValueError(f"Could not find 'as of' date on {url}")
    as_of_date = datetime.strptime(m.group(1), "%m/%d/%Y").date()

    table = soup.find("table", id="cotton-on-call")
    if table is None:
        raise ValueError(f"Could not find data table on {url}")

    rows = []
    for tr in table.find_all("tr"):
        th = tr.find("th", attrs={"axis": ["date", "total"]})
        if not th:
            continue
        fut_label = " ".join(th.get_text(strip=True).split())
        tds = tr.find_all("td")
        if len(tds) < 6:
            continue
        vals = [_clean_int(td.get_text()) for td in tds[:6]]
        rows.append((fut_label, *vals))

    return as_of_date, rows


def rows_to_long(as_of_date: datetime.date, rows: list[tuple]) -> pd.DataFrame:
    date_str = f"{as_of_date.month}/{as_of_date.day}/{as_of_date.year}"
    records = []
    for fut_label, sales, s_chg, purch, p_chg, oi, oi_chg in rows:
        for tag, value in zip(TAGS, (sales, s_chg, purch, p_chg, oi, oi_chg)):
            records.append({
                "Date": date_str,
                "Fut": fut_label,
                "Tag": tag,
                "Value": value,
                "month": as_of_date.month,
                "year": as_of_date.year,
            })
    return pd.DataFrame.from_records(records, columns=COLUMNS)


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


def update(rebuild: bool = False) -> pd.DataFrame:
    master = pd.DataFrame(columns=COLUMNS) if rebuild else load_master()
    last_date = None if rebuild else latest_date(master)

    reports = list_reports()
    new_frames = []
    for report in reports:
        if report["release_date"] is None:
            continue
        # data as-of date is always a few days before the release date; skip
        # reports whose release date is not after our last known as-of date
        # (cheap pre-filter, exact check happens after parsing).
        if last_date is not None and report["release_date"] <= last_date:
            continue
        try:
            as_of_date, rows = parse_report(report["url"])
        except Exception as exc:  # noqa: BLE001
            print(f"  ! skipped {report['url']}: {exc}", file=sys.stderr)
            continue
        if last_date is not None and as_of_date <= last_date:
            continue
        if not rows:
            continue
        print(f"  + {report['label']} -> as of {as_of_date} ({len(rows)} futures)")
        new_frames.append(rows_to_long(as_of_date, rows))

    if new_frames:
        master = pd.concat([master] + new_frames, ignore_index=True)
        master = master.drop_duplicates(subset=["Date", "Fut", "Tag"], keep="last")
        master = master.sort_values(["year", "month", "Date"]).reset_index(drop=True)

    return master


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true", help="rebuild master from Old Database.csv + full site history")
    args = parser.parse_args()

    print("Fetching Cotton On-Call report index...")
    master = update(rebuild=args.rebuild)

    DB_DIR.mkdir(parents=True, exist_ok=True)
    master.to_csv(MASTER_CSV, index=False)
    print(f"Master database written: {MASTER_CSV} ({len(master)} rows)")

    if master.empty:
        print("Master database is empty after update - treating as a failure.", file=sys.stderr)
        sys.exit(1)

    issues = health_check(master)
    if issues:
        print("Data health issues found (non-fatal, reported in notify email):")
        for issue in issues:
            print(f"  ! {issue}")
    else:
        print("Data health check: OK")


if __name__ == "__main__":
    main()
