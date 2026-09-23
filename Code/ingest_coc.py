"""
Cotton On-Call (COC) ingest pipeline.

Source: CFTC Historical Cotton On-Call reports
  Index : https://www.cftc.gov/MarketReports/CottonOnCall/HistoricalCottonOn-Call/index.htm
  Report: https://www.cftc.gov/MarketReports/CottonOnCall/HistoricalCottonOn-Call/deaoncall{MMDDYY}.html

Reports are released weekly (Thursday, ~3:30pm ET) and carry data "as of" the
previous Friday. This script scrapes the index page for every report link,
skips any report whose as-of date is already in the master database, parses
new reports, and appends them in a long format (Date, Fut, Tag, Value, month,
year).

Usage:
    python ingest_coc.py            # update the master database with new reports
    python ingest_coc.py --rebuild  # rebuild master by re-scraping every report
                                     # CFTC's site currently hosts (see full_backfill()).
                                     # Old Database.csv is only used as a fallback for
                                     # dates older than CFTC's earliest hosted report.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime

import pandas as pd
import requests
from bs4 import BeautifulSoup

from coc_health import (  # noqa: E402
    COLUMNS,
    DB_DIR,
    MASTER_CSV,
    OLD_CSV,
    TAG_FIXUPS,
    _normalize_fut_label,
    health_check,
    latest_date,
    load_master,
    refresh_rollex_ct_snapshot,
)

BASE = "https://www.cftc.gov"
INDEX_URL = f"{BASE}/MarketReports/CottonOnCall/HistoricalCottonOn-Call/index.htm"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

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


_INT_RE = re.compile(r"-?[\d,]+")


def _clean_int(text: str) -> int:
    """Strip footnote markers etc. (e.g. "-1,627 *") and parse the leading number."""
    text = text.replace("\xa0", "")
    m = _INT_RE.search(text)
    if not m:
        return 0
    return int(m.group(0).replace(",", ""))


_ROW_LABEL_RE = re.compile(r"^[A-Za-z]+ \d{4}$")


def _extract_table_rows(table) -> list[tuple]:
    """A data row is any <tr> whose first cell reads "Month YYYY" or "Totals" and
    is followed by 6 more cells. This is deliberately markup-agnostic (th vs td,
    axis attributes or none) because the CFTC page structure changed at least 3
    times across the report's ~20-year history - matching by content instead of
    by tag/attribute survives all of them."""
    rows = []
    for tr in table.find_all("tr"):
        cells = tr.find_all(["th", "td"])
        if len(cells) < 7:
            continue
        label = " ".join(cells[0].get_text(strip=True).split())
        if not (_ROW_LABEL_RE.match(label) or label.lower() == "totals"):
            continue
        vals = [_clean_int(c.get_text()) for c in cells[1:7]]
        rows.append((_normalize_fut_label(label if label.lower() != "totals" else "Totals"), *vals))
    return rows


def parse_report(url: str) -> tuple[datetime.date, list[tuple]]:
    """Parse a single COC report page. Returns (as_of_date, rows).

    Each row is (fut_label, sales, s_change, purchase, p_change, oi, oi_change).
    """
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    text = soup.get_text()
    m = re.search(r"as\s+of\s+(\d{2}/\d{2}/\d{4})", text)
    if m:
        as_of_date = datetime.strptime(m.group(1), "%m/%d/%Y").date()
    else:
        m = re.search(r"as\s+of\s+([A-Za-z]{3,9}\s+\d{1,2},\s*\d{4})", text)
        if m:
            raw = m.group(1)
            try:
                as_of_date = datetime.strptime(raw, "%B %d, %Y").date()
            except ValueError:
                as_of_date = datetime.strptime(raw, "%b %d, %Y").date()
        else:
            m = re.search(r"as\s+of\s+(\d{2}/\d{2}/\d{2})(?!\d)", text)
            if not m:
                raise ValueError(f"Could not find 'as of' date on {url}")
            as_of_date = datetime.strptime(m.group(1), "%m/%d/%y").date()

    if as_of_date.year < 2000:
        raise ValueError(f"Implausible as-of date {as_of_date} parsed on {url}")

    best_rows: list[tuple] = []
    for cand in soup.find_all("table"):
        cand_rows = _extract_table_rows(cand)
        if len(cand_rows) > len(best_rows):
            best_rows = cand_rows

    if not best_rows:
        raise ValueError(f"Could not find data table on {url}")

    return as_of_date, best_rows


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


def scrape_all_reports(max_workers: int = 10) -> tuple[dict, list[tuple[str, str]]]:
    """Fetch + parse every report currently listed on CFTC's historical index
    (concurrently - ~1300+ reports would take too long sequentially). Returns
    ({as_of_date: rows}, [(url, error), ...])."""
    import concurrent.futures as cf

    reports = list_reports()
    results: dict = {}
    errors: list[tuple[str, str]] = []
    with cf.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(parse_report, r["url"]): r for r in reports if r["url"]}
        done = 0
        for fut in cf.as_completed(futures):
            r = futures[fut]
            done += 1
            try:
                as_of_date, rows = fut.result()
                if rows:
                    results[as_of_date] = rows
            except Exception as exc:  # noqa: BLE001
                errors.append((r["url"], str(exc)))
            if done % 100 == 0 or done == len(futures):
                print(f"  ... {done}/{len(futures)} reports fetched ({len(errors)} failed)")
    return results, errors


def full_backfill() -> pd.DataFrame:
    """Rebuild the master database by re-scraping every report CFTC's site still
    hosts (correctly labelled, full 4-digit contract years), instead of trusting
    Old Database.csv for that whole span. That legacy file was found to have
    genuine label/value corruption for ~2009-2020 (the same "Month YY" label
    reused 2-3x per date for different real contract years, with values not even
    reliably in occurrence order) - not fixable by relabelling, only by getting
    the real numbers from the source. Old Database.csv is only used for dates
    older than the earliest report CFTC's site still hosts."""
    print("Full backfill: scraping every report on CFTC's historical index...")
    scraped, errors = scrape_all_reports()
    if errors:
        print(f"  ! {len(errors)} report(s) failed to parse:")
        for url, err in errors[:20]:
            print(f"    - {url}: {err}")

    frames = [rows_to_long(d, rows) for d, rows in scraped.items()]
    scraped_master = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS)
    earliest_scraped = min(scraped) if scraped else None
    print(f"  Scraped {len(scraped)} reports, earliest as-of date: {earliest_scraped}")

    legacy = pd.DataFrame(columns=COLUMNS)
    if OLD_CSV.exists():
        legacy = pd.read_csv(OLD_CSV, parse_dates=False)[COLUMNS]
        legacy["Tag"] = legacy["Tag"].replace(TAG_FIXUPS)
        legacy["Fut"] = legacy["Fut"].apply(_normalize_fut_label)
        legacy["Value"] = pd.to_numeric(legacy["Value"].astype(str).str.replace(",", "", regex=False), errors="coerce").fillna(0).astype(int)
        if earliest_scraped is not None:
            legacy_dates = pd.to_datetime(legacy["Date"], format="%m/%d/%Y").dt.date
            before = len(legacy)
            legacy = legacy[legacy_dates < earliest_scraped]
            print(f"  Keeping {len(legacy)}/{before} legacy rows strictly before {earliest_scraped} (CFTC doesn't host anything older).")

    master = pd.concat([legacy, scraped_master], ignore_index=True)
    master = master.drop_duplicates()  # exact full-row duplicates only - safe, unlike subset-based dedup
    master = master.sort_values(["year", "month", "Date"]).reset_index(drop=True)
    return master


def update(rebuild: bool = False) -> pd.DataFrame:
    if rebuild:
        return full_backfill()

    master = load_master()
    last_date = latest_date(master)

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
        master = master.drop_duplicates()  # exact full-row duplicates only - safe
        master = master.sort_values(["year", "month", "Date"]).reset_index(drop=True)

    return master


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true", help="rebuild master from Old Database.csv + full site history")
    args = parser.parse_args()

    print("Fetching Cotton On-Call report index...")
    master = update(rebuild=args.rebuild)

    DB_DIR.mkdir(parents=True, exist_ok=True)
    master.to_csv(MASTER_CSV, index=False)
    print(f"Master database written: {MASTER_CSV} ({len(master)} rows)")

    if refresh_rollex_ct_snapshot():
        print("CT Rollex price snapshot refreshed for the dashboard.")
    else:
        print("CT Rollex live parquet not reachable - snapshot left as-is (expected off the desk machine).")

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
