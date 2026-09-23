"""
notify.py - Cotton On-Call Automator email summary
Usage: python notify.py <status> <git_status>
  status     : ok | error
  git_status : pushed | skipped | failed
"""

import sys
import datetime
from pathlib import Path

import pandas as pd

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR / "Code"))
from ingest_coc import health_check, MASTER_CSV  # noqa: E402

TO_EMAIL = "virat.arya@etgworld.com"

status     = sys.argv[1] if len(sys.argv) > 1 else "ok"
git_status = sys.argv[2] if len(sys.argv) > 2 else "unknown"
run_dt     = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
today      = datetime.date.today().strftime("%Y-%m-%d")


def coc_summary() -> str:
    if not MASTER_CSV.exists():
        return "  MASTER DATABASE NOT FOUND"
    df = pd.read_csv(MASTER_CSV)
    df["Value"] = pd.to_numeric(df["Value"].astype(str).str.replace(",", "", regex=False), errors="coerce").fillna(0).astype(int)
    totals = df[df["Fut"] == "Totals"].copy()
    totals["DateDT"] = pd.to_datetime(totals["Date"], format="%m/%d/%Y")
    tw = totals.pivot_table(index="DateDT", columns="Tag", values="Value", aggfunc="last").sort_index()

    if tw.empty:
        return "  NO DATA"

    latest = tw.iloc[-1]
    latest_date = tw.index[-1].date()
    lines = [
        f"  As of        : {latest_date}",
        f"  Rows         : {len(df):,}   (history {tw.index.min().date()} -> {tw.index.max().date()})",
        f"  Unfixed Sales: {latest['Sales']:>10,.0f}   ({latest['S Change']:+,.0f} WoW)",
        f"  Unfixed Purch: {latest['Purchase']:>10,.0f}   ({latest['P Change']:+,.0f} WoW)",
        f"  Open Interest: {latest['OI']:>10,.0f}   ({latest['OI Change']:+,.0f} WoW)",
    ]
    return "\n".join(lines), df


def health_lines(df) -> str:
    issues = health_check(df)
    if not issues:
        return "  No issues found."
    return "\n".join(f"  ! {issue}" for issue in issues)


def send_outlook_email(subject: str, body: str):
    try:
        import win32com.client
        outlook      = win32com.client.Dispatch("Outlook.Application")
        mail         = outlook.CreateItem(0)
        mail.To      = TO_EMAIL
        mail.Subject = subject
        mail.Body    = body
        mail.Send()
        print(f"  Email sent -> {TO_EMAIL}")
    except Exception as e:
        print(f"  Email failed: {e}")


ok  = status == "ok"
tag = "[OK]" if ok else "[ERROR]"
subject = f"{tag} Cotton-On-Call — {today}"

git_line = {
    "pushed":  "GitHub  : Pushed successfully",
    "skipped": "GitHub  : No changes - push skipped",
    "failed":  "GitHub  : PUSH FAILED",
}.get(git_status, f"GitHub  : {git_status}")

summary_result = coc_summary()
if isinstance(summary_result, tuple):
    summary_text, df_for_health = summary_result
    health_text = health_lines(df_for_health)
else:
    summary_text = summary_result
    health_text = "  Skipped (no data)."

body = f"""Cotton On-Call — Daily Update
Run time : {run_dt}
Status   : {"OK" if ok else "ERROR - ingest failed, check run_log.txt"}
{git_line}

{"=" * 60}
COTTON ON-CALL SUMMARY
{"=" * 60}
{summary_text}

{"=" * 60}
DATA HEALTH
{"=" * 60}
{health_text}

Source: CFTC weekly Cotton On-Call report (Thursdays ~3:30pm ET, data as-of
the previous Friday). Report cadence can shift a few days around federal
holidays - staleness/gap warnings above reflect that, not necessarily a
pipeline failure.

Log: C:\\Users\\virat.arya\\ETG\\SoftsDatabase - Documents\\Database\\Hardmine\\Fundamental\\Cotton_Calls\\Automator\\run_log.txt
"""

print(body)
send_outlook_email(subject, body)
