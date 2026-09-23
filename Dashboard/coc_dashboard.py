import sys
import warnings
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

warnings.filterwarnings("ignore")

APP_DIR = Path(__file__).resolve().parent
REPO_DIR = APP_DIR.parent
DB_DIR = REPO_DIR / "Database"
MASTER_CSV = DB_DIR / "Cotton_On_Call_Database.csv"

sys.path.insert(0, str(REPO_DIR / "Code"))
from coc_health import ROLLEX_CT_LIVE_PATH, ROLLEX_CT_SNAPSHOT, health_check  # noqa: E402

NAVY = "#0a2463"
TEAL = "#1f8a9c"
GREEN = "#1f9d6f"
RED = "#c94a4a"
AMBER = "#c98a1f"

st.set_page_config(page_title="Cotton On-Call", layout="wide")

# Force a strict light theme regardless of the viewer's OS/browser dark-mode
# setting — CSS below hard-codes colours (no prefers-color-scheme query) and
# .streamlit/config.toml pins base="light" so Streamlit's own chrome doesn't
# switch either.
st.markdown(
    """
<style>
[data-testid="stAppViewContainer"], [data-testid="stMain"], .main {
    background: #fafafa !important;
}
[data-testid="stHeader"] { background: #fafafa !important; }
[data-testid="stSidebar"] {
    background: #f0f2f8 !important;
    border-right: 1px solid #dfe3ee;
}
h1, h2, h3, h4, h5, h6 { color: #0a2463 !important; }
p, span, label, div { color: #1a1a2e; }
[data-testid="stSidebar"] * { color: #1a1a2e !important; }

/* Pill / segmented-control tabs */
.stTabs [data-baseweb="tab-list"] {
    background: #eef0f6;
    padding: 4px;
    border-radius: 999px;
    gap: 4px;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    color: #4a5578 !important;
    border-radius: 999px !important;
    padding: 8px 20px !important;
    font-weight: 600;
    border: none !important;
}
.stTabs [aria-selected="true"] { background: #0a2463 !important; color: #fff !important; }
.stTabs [data-baseweb="tab-highlight"] { display: none !important; }
.stTabs [data-baseweb="tab-border"] { display: none !important; }

.stDataFrame { background: #ffffff; }
.card-desc { color: #5a6688; font-size: 0.85rem; margin-top: -6px; margin-bottom: 10px; }

/* Multiselect: selected pills (navy bg, white text) + open dropdown menu (white bg, dark text) */
[data-baseweb="tag"] { background-color: #0a2463 !important; }
[data-baseweb="tag"] span { color: #ffffff !important; }
[data-baseweb="popover"] [data-baseweb="menu"] { background: #ffffff !important; }
[data-baseweb="popover"] [data-baseweb="menu"] li,
[data-baseweb="popover"] [data-baseweb="menu"] li * { color: #1a1a2e !important; }
[data-baseweb="select"] { background: #ffffff !important; }
[data-baseweb="select"] * { color: #1a1a2e !important; }
</style>
""",
    unsafe_allow_html=True,
)


def kpi_row(cards):
    """cards: list of (label, value, subtext, accent_color)"""
    html = "<div style='display:flex;gap:12px;margin-bottom:18px;flex-wrap:wrap;'>"
    for label, value, sub, color in cards:
        html += f"""
        <div style='flex:1;min-width:160px;background:#ffffff;
            border-top:3px solid {color};border-radius:8px;padding:12px 16px;
            box-shadow:0 1px 3px rgba(10,36,99,0.08);'>
            <div style='font-size:11px;letter-spacing:0.09em;text-transform:uppercase;color:#7a86a8;'>{label}</div>
            <div style='font-size:27px;font-weight:700;color:#0a2463;margin-top:2px;'>{value}</div>
            <div style='font-size:11px;color:#5a6688;margin-top:2px;'>{sub}</div>
        </div>"""
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def chart_layout(fig, **extra):
    xaxis = dict(gridcolor="rgba(10,36,99,0.08)", color="#4a5578")
    yaxis = dict(gridcolor="rgba(10,36,99,0.08)", color="#4a5578")
    xaxis.update(extra.pop("xaxis", {}))
    yaxis.update(extra.pop("yaxis", {}))
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#1a1a2e"),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        xaxis=xaxis,
        yaxis=yaxis,
        margin=dict(t=30, b=30, l=10, r=10),
        **extra,
    )
    return fig


@st.cache_data(ttl=600)
def load_master() -> pd.DataFrame:
    df = pd.read_csv(MASTER_CSV)
    df["DateDT"] = pd.to_datetime(df["Date"], format="%m/%d/%Y")
    return df


@st.cache_data(ttl=600)
def load_rollex_ct():
    """Prefer the live desk-machine parquet (freshest); fall back to the repo
    copy the Automator ships, which is what makes this work on Streamlit
    Cloud (no access to the desk machine's filesystem)."""
    path = ROLLEX_CT_LIVE_PATH if ROLLEX_CT_LIVE_PATH.exists() else ROLLEX_CT_SNAPSHOT
    if not path.exists():
        return None
    rdf = pd.read_parquet(path, columns=["rollex_px"])
    rdf.index = pd.to_datetime(rdf.index)
    return rdf.rename(columns={"rollex_px": "CT"})


df = load_master()
totals = df[df["Fut"] == "Totals"].copy()
totals_wide = totals.pivot_table(index="DateDT", columns="Tag", values="Value", aggfunc="last").sort_index()

st.title("Cotton On-Call")
st.caption("CFTC weekly report — unfixed call cotton sales/purchases and open ICE futures interest, by contract month.")

# ── SIDEBAR FILTERS ──────────────────────────────────────────────────────────
min_d, max_d = totals_wide.index.min().date(), totals_wide.index.max().date()
with st.sidebar:
    st.subheader("Filters")
    date_range = st.slider("As-of date range", min_value=min_d, max_value=max_d, value=(max(min_d, max_d.replace(year=max_d.year - 3)), max_d))
    fut_months = sorted(df.loc[df["Fut"] != "Totals", "Fut"].unique(), key=lambda x: (x.split()[-1], x.split()[0]))
    selected_fut = st.multiselect("Contract month(s) (for tab 2)", fut_months)

mask = (totals_wide.index.date >= date_range[0]) & (totals_wide.index.date <= date_range[1])
tv = totals_wide.loc[mask]

# ── KPI ROW (latest report) ──────────────────────────────────────────────────
latest = totals_wide.iloc[-1]
latest_date = totals_wide.index[-1].date()
kpi_row([
    ("As of", latest_date.strftime("%b %d, %Y"), f"{(datetime.today().date() - latest_date).days}d old", TEAL),
    ("Unfixed Sales", f"{latest['Sales']:,.0f}", f"{latest['S Change']:+,.0f} WoW", GREEN if latest["S Change"] >= 0 else RED),
    ("Unfixed Purchases", f"{latest['Purchase']:,.0f}", f"{latest['P Change']:+,.0f} WoW", GREEN if latest["P Change"] >= 0 else RED),
    ("Open Interest", f"{latest['OI']:,.0f}", f"{latest['OI Change']:+,.0f} WoW", AMBER),
])

tab1, tab2, tab3, tab4 = st.tabs(["Totals Over Time", "By Contract Month", "Price Link (CT Rollex)", "Data Health"])

# ── TAB 1: TOTALS OVER TIME ──────────────────────────────────────────────────
with tab1:
    st.markdown("<div class='card-desc'>Weekly totals across all contract months: unfixed call sales/purchases and open ICE futures interest.</div>", unsafe_allow_html=True)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=tv.index, y=tv["Sales"], name="Unfixed Sales", line=dict(color=RED, width=2)))
    fig.add_trace(go.Scatter(x=tv.index, y=tv["Purchase"], name="Unfixed Purchases", line=dict(color=GREEN, width=2)))
    fig.add_trace(go.Scatter(x=tv.index, y=tv["OI"], name="Open Interest", line=dict(color=TEAL, width=2), yaxis="y2"))
    chart_layout(fig, height=440, yaxis2=dict(overlaying="y", side="right", gridcolor="rgba(0,0,0,0)", color="#4a5578", title="Open Interest"))
    st.plotly_chart(fig, width='stretch')

    st.markdown("<div class='card-desc'>Week-over-week change (net of price-fixing activity).</div>", unsafe_allow_html=True)
    fig2 = go.Figure()
    fig2.add_trace(go.Bar(x=tv.index, y=tv["S Change"], name="S Change", marker_color=RED))
    fig2.add_trace(go.Bar(x=tv.index, y=tv["P Change"], name="P Change", marker_color=GREEN))
    fig2.add_trace(go.Bar(x=tv.index, y=tv["OI Change"], name="OI Change", marker_color=TEAL))
    chart_layout(fig2, height=340, barmode="group")
    st.plotly_chart(fig2, width='stretch')

# ── TAB 2: BY CONTRACT MONTH ─────────────────────────────────────────────────
with tab2:
    st.markdown("<div class='card-desc'>Latest report snapshot, broken out by ICE futures contract month.</div>", unsafe_allow_html=True)
    latest_all = df[df["DateDT"] == totals_wide.index[-1]]
    latest_by_fut = latest_all[latest_all["Fut"] != "Totals"].pivot_table(index="Fut", columns="Tag", values="Value", aggfunc="last")
    latest_by_fut = latest_by_fut.loc[(latest_by_fut[["Sales", "Purchase", "OI"]].sum(axis=1) > 0)]

    fig3 = go.Figure()
    fig3.add_trace(go.Bar(x=latest_by_fut.index, y=latest_by_fut["Sales"], name="Unfixed Sales", marker_color=RED))
    fig3.add_trace(go.Bar(x=latest_by_fut.index, y=latest_by_fut["Purchase"], name="Unfixed Purchases", marker_color=GREEN))
    chart_layout(fig3, height=380, barmode="group")
    st.plotly_chart(fig3, width='stretch')

    if selected_fut:
        st.markdown("<div class='card-desc'>History for selected contract month(s).</div>", unsafe_allow_html=True)
        fsub = df[(df["Fut"].isin(selected_fut)) & (df["DateDT"].dt.date >= date_range[0]) & (df["DateDT"].dt.date <= date_range[1])]
        fw = fsub.pivot_table(index=["DateDT", "Fut"], columns="Tag", values="Value", aggfunc="last").reset_index()
        fig4 = go.Figure()
        for fm in selected_fut:
            sub = fw[fw["Fut"] == fm].sort_values("DateDT")
            fig4.add_trace(go.Scatter(x=sub["DateDT"], y=sub["OI"], name=f"{fm} OI", mode="lines"))
        chart_layout(fig4, height=360)
        st.plotly_chart(fig4, width='stretch')

    st.dataframe(latest_by_fut[["Sales", "S Change", "Purchase", "P Change", "OI", "OI Change"]].style.format("{:,.0f}"), width='stretch')

# ── TAB 3: PRICE LINK (CT ROLLEX) ────────────────────────────────────────────
with tab3:
    st.markdown(
        "<div class='card-desc'>Links weekly On-Call totals to the CT continuous roll-adjusted price "
        "(<code>rollex_CT.parquet</code>, refreshed daily by the Rollex pipeline) to see whether on-call "
        "positioning changes lead, lag, or track price moves.</div>",
        unsafe_allow_html=True,
    )
    rollex = load_rollex_ct()
    if rollex is None:
        st.info("CT Rollex price data isn't available in this environment yet — it ships as a snapshot refreshed by the Automator on the desk machine.")
    else:
        merged = tv.join(rollex, how="inner")
        merged["px_change"] = merged["CT"].diff()
        merged = merged.dropna(subset=["px_change"])

        fig5 = go.Figure()
        fig5.add_trace(go.Scatter(x=merged.index, y=merged["CT"], name="CT price (rollex_px)", line=dict(color=AMBER, width=2)))
        fig5.add_trace(go.Bar(x=merged.index, y=merged["OI Change"], name="OI Change (On-Call)", marker_color=TEAL, yaxis="y2", opacity=0.6))
        chart_layout(fig5, height=400, yaxis2=dict(overlaying="y", side="right", gridcolor="rgba(0,0,0,0)", color="#4a5578", title="OI Change"))
        st.plotly_chart(fig5, width='stretch')

        corr_cols = st.columns(3)
        for col, tag, label in zip(corr_cols, ["S Change", "P Change", "OI Change"], ["Sales chg", "Purchases chg", "OI chg"]):
            r = merged["px_change"].corr(merged[tag])
            col.markdown(
                f"<div style='background:#ffffff;border-radius:8px;padding:10px 14px;"
                f"box-shadow:0 1px 3px rgba(10,36,99,0.08);'>"
                f"<div style='font-size:11px;color:#7a86a8;text-transform:uppercase;'>corr(price chg, {label})</div>"
                f"<div style='font-size:22px;font-weight:700;color:#0a2463;'>{r:+.2f}</div></div>",
                unsafe_allow_html=True,
            )

        fig6 = go.Figure()
        fig6.add_trace(go.Scatter(x=merged["OI Change"], y=merged["px_change"], mode="markers", marker=dict(color=TEAL, size=7, opacity=0.7)))
        chart_layout(fig6, height=340, xaxis=dict(title="Weekly OI Change (On-Call)"), yaxis=dict(title="Weekly CT price change"))
        st.plotly_chart(fig6, width='stretch')
        st.caption("Weekly change measured Friday-as-of-date to Friday-as-of-date (the report's own weekly cadence).")

# ── TAB 4: DATA HEALTH ───────────────────────────────────────────────────────
with tab4:
    st.markdown("<div class='card-desc'>Sanity checks on the master database — freshness, gaps, duplicates, completeness.</div>", unsafe_allow_html=True)
    issues = health_check(df)
    if not issues:
        st.markdown(f"<div style='color:{GREEN};font-weight:600;'>No issues found.</div>", unsafe_allow_html=True)
    else:
        for issue in issues:
            st.markdown(f"<div style='color:{AMBER};padding:4px 0;'>&#9888; {issue}</div>", unsafe_allow_html=True)

    st.caption(f"{len(df):,} rows · {totals_wide.shape[0]:,} report dates · {totals_wide.index.min().strftime('%Y-%m-%d')} to {totals_wide.index.max().strftime('%Y-%m-%d')}")
