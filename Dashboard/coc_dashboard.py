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

ROLLEX_CT_PATH = Path(
    r"C:\Users\virat.arya\ETG\SoftsDatabase - Documents\Database\Hardmine\LSEG\Rollex\Database\rollex_CT.parquet"
)

sys.path.insert(0, str(REPO_DIR / "Code"))
from ingest_coc import health_check  # noqa: E402

TEAL = "#4FB0C8"
GREEN = "#2dc6a0"
RED = "#e05c6a"
AMBER = "#e0a84a"

st.set_page_config(page_title="Cotton On-Call", layout="wide")

st.markdown(
    """
<style>
[data-testid="stAppViewContainer"], [data-testid="stMain"] {
    background:
        radial-gradient(ellipse 70% 60% at 20% 80%, rgba(26,74,90,.50) 0%, transparent 65%),
        radial-gradient(ellipse 60% 50% at 80% 20%, rgba(42,85,104,.45) 0%, transparent 60%),
        radial-gradient(ellipse 80% 70% at 50% 30%, rgba(79,176,200,.10) 0%, transparent 55%),
        #0D1620 !important;
    background-attachment: fixed;
}
[data-testid="stHeader"] {
    background: rgba(13,22,32,.85) !important;
    backdrop-filter: saturate(180%) blur(16px);
    border-bottom: 1px solid rgba(188,212,222,.14);
}
[data-testid="stSidebar"] {
    background: rgba(13,22,32,.92) !important;
    border-right: 1px solid rgba(188,212,222,.14);
}
h1, h2, h3, h4, h5, h6 { color: #e8f4f8 !important; }
p, span, label, div { color: #d6e8ee; }
[data-testid="stSidebar"] * { color: #d6e8ee !important; }
.stTabs [data-baseweb="tab"] {
    background: rgba(255,255,255,0.03);
    color: #7fa8b8 !important;
    border-radius: 6px 6px 0 0;
}
.stTabs [aria-selected="true"] { background: rgba(79,176,200,.18) !important; color: #e8f4f8 !important; }
.stDataFrame { background: rgba(13,22,32,.5); }
.card-desc { color: #7fa8b8; font-size: 0.85rem; margin-top: -6px; margin-bottom: 10px; }
</style>
""",
    unsafe_allow_html=True,
)


def kpi_row(cards):
    """cards: list of (label, value, subtext, accent_color)"""
    html = "<div style='display:flex;gap:12px;margin-bottom:18px;flex-wrap:wrap;'>"
    for label, value, sub, color in cards:
        html += f"""
        <div style='flex:1;min-width:160px;background:rgba(13,28,42,.75);
            border-top:3px solid {color};border-radius:8px;padding:12px 16px;
            backdrop-filter:blur(6px);'>
            <div style='font-size:11px;letter-spacing:0.09em;text-transform:uppercase;color:#5e8fa0;'>{label}</div>
            <div style='font-size:27px;font-weight:700;color:#e8f4f8;margin-top:2px;'>{value}</div>
            <div style='font-size:11px;color:#3d6878;margin-top:2px;'>{sub}</div>
        </div>"""
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def chart_layout(fig, **extra):
    xaxis = dict(gridcolor="rgba(255,255,255,0.06)", color="#7fa8b8")
    yaxis = dict(gridcolor="rgba(255,255,255,0.06)", color="#7fa8b8")
    xaxis.update(extra.pop("xaxis", {}))
    yaxis.update(extra.pop("yaxis", {}))
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#d6e8ee"),
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
    if not ROLLEX_CT_PATH.exists():
        return None
    rdf = pd.read_parquet(ROLLEX_CT_PATH)
    rdf.index = pd.to_datetime(rdf.index)
    return rdf[["rollex_px"]].rename(columns={"rollex_px": "CT"})


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
    chart_layout(fig, height=440, yaxis2=dict(overlaying="y", side="right", gridcolor="rgba(0,0,0,0)", color="#7fa8b8", title="Open Interest"))
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
        st.warning(f"Could not find {ROLLEX_CT_PATH}")
    else:
        merged = tv.join(rollex, how="inner")
        merged["px_change"] = merged["CT"].diff()
        merged = merged.dropna(subset=["px_change"])

        fig5 = go.Figure()
        fig5.add_trace(go.Scatter(x=merged.index, y=merged["CT"], name="CT price (rollex_px)", line=dict(color=AMBER, width=2)))
        fig5.add_trace(go.Bar(x=merged.index, y=merged["OI Change"], name="OI Change (On-Call)", marker_color=TEAL, yaxis="y2", opacity=0.6))
        chart_layout(fig5, height=400, yaxis2=dict(overlaying="y", side="right", gridcolor="rgba(0,0,0,0)", color="#7fa8b8", title="OI Change"))
        st.plotly_chart(fig5, width='stretch')

        corr_cols = st.columns(3)
        for col, tag, label in zip(corr_cols, ["S Change", "P Change", "OI Change"], ["Sales chg", "Purchases chg", "OI chg"]):
            r = merged["px_change"].corr(merged[tag])
            col.markdown(
                f"<div style='background:rgba(13,28,42,.75);border-radius:8px;padding:10px 14px;'>"
                f"<div style='font-size:11px;color:#5e8fa0;text-transform:uppercase;'>corr(price chg, {label})</div>"
                f"<div style='font-size:22px;font-weight:700;color:#e8f4f8;'>{r:+.2f}</div></div>",
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

    kpi_row([
        ("Total rows", f"{len(df):,}", "", TEAL),
        ("Unique report dates", f"{totals_wide.shape[0]:,}", "", TEAL),
        ("History start", totals_wide.index.min().strftime("%Y-%m-%d"), "", TEAL),
        ("History end", totals_wide.index.max().strftime("%Y-%m-%d"), "", TEAL),
    ])
