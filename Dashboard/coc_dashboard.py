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
from coc_health import ROLLEX_CT_LIVE_PATH, ROLLEX_CT_SNAPSHOT, fut_expiry_date, health_check  # noqa: E402

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
body, .main { color: #1a1a2e; }
[data-testid="stSidebar"] { color: #1a1a2e; }

/* Streamlit's default tab look, kept as-is on purpose - custom pill styling here kept
   breaking (child text elements have their own explicit colour that beats an inherited
   colour on the parent tab, even with !important on the parent), so we no longer fight
   it with CSS. Only make sure the selected-tab underline/text stay visible on light bg. */
.stTabs [aria-selected="true"] { color: #0a2463 !important; font-weight: 700; }

.stDataFrame { background: #ffffff; }
.card-desc { color: #5a6688; font-size: 0.85rem; margin-top: -6px; margin-bottom: 10px; }

/* Multiselect: selected pills (navy bg, white text) + open dropdown menu (white bg, dark text) */
span[data-baseweb="tag"],
span[data-baseweb="tag"] div,
span[data-baseweb="tag"] span {
    background-color: #0a2463 !important;
    color: #ffffff !important;
    fill: #ffffff !important;
}
span[data-baseweb="tag"] svg { fill: #ffffff !important; }
[data-baseweb="popover"] [data-baseweb="menu"] { background: #ffffff !important; }
[data-baseweb="popover"] [data-baseweb="menu"] li,
[data-baseweb="popover"] [data-baseweb="menu"] li * { color: #1a1a2e !important; }
[data-baseweb="select"] { background: #ffffff !important; }
[data-baseweb="select"] > div { background: #ffffff !important; color: #1a1a2e !important; }
[data-testid="stSidebar"] span[data-baseweb="tag"],
[data-testid="stSidebar"] span[data-baseweb="tag"] * { color: #ffffff !important; }

/* Small filter-summary text in the sidebar (replaces top KPI cards) */
.filter-stat { font-size: 12px; color: #5a6688 !important; line-height: 1.7; margin-bottom: 14px; }
.filter-stat b { color: #0a2463 !important; font-size: 13px; }
</style>
""",
    unsafe_allow_html=True,
)


def sidebar_stats(rows):
    """rows: list of (label, value, subtext) - small text, not cards."""
    html = "<div class='filter-stat'>"
    for label, value, sub in rows:
        html += f"{label}: <b>{value}</b>" + (f" <span style='color:#7a86a8;'>({sub})</span>" if sub else "") + "<br>"
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

latest = totals_wide.iloc[-1]
latest_date = totals_wide.index[-1].date()

# ── SIDEBAR FILTERS ──────────────────────────────────────────────────────────
min_d, max_d = totals_wide.index.min().date(), totals_wide.index.max().date()
with st.sidebar:
    st.subheader("Filters")
    default_start = max(min_d, max_d.replace(year=max_d.year - 3))
    dc1, dc2 = st.columns(2)
    start_d = dc1.date_input("From", value=default_start, min_value=min_d, max_value=max_d)
    end_d = dc2.date_input("To", value=max_d, min_value=min_d, max_value=max_d)
    date_range = st.slider("Drag to adjust", min_value=min_d, max_value=max_d, value=(start_d, end_d))
    fut_months = sorted(df.loc[df["Fut"] != "Totals", "Fut"].unique(), key=fut_expiry_date)
    selected_fut = st.multiselect("Contract month(s) (for tab 2)", fut_months)

    st.divider()
    sidebar_stats([
        ("As of", latest_date.strftime("%b %d, %Y"), f"{(datetime.today().date() - latest_date).days}d old"),
        ("Unfixed Sales", f"{latest['Sales']:,.0f}", f"{latest['S Change']:+,.0f} WoW"),
        ("Unfixed Purchases", f"{latest['Purchase']:,.0f}", f"{latest['P Change']:+,.0f} WoW"),
        ("Open Interest", f"{latest['OI']:,.0f}", f"{latest['OI Change']:+,.0f} WoW"),
    ])

mask = (totals_wide.index.date >= date_range[0]) & (totals_wide.index.date <= date_range[1])
tv = totals_wide.loc[mask]

tab1, tab2, tab_heatmap, tab_season, tab3, tab_expiry, tab4 = st.tabs([
    "Totals Over Time", "By Contract Month", "Imbalance Heatmap", "Seasonality",
    "Price Link (CT Rollex)", "Expiry Watch (POC)", "Data Health",
])

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
    st.markdown("<div class='card-desc'>Latest report snapshot, broken out by ICE futures contract month - nearest expiry first.</div>", unsafe_allow_html=True)
    latest_all = df[df["DateDT"] == totals_wide.index[-1]]
    latest_by_fut = latest_all[latest_all["Fut"] != "Totals"].pivot_table(index="Fut", columns="Tag", values="Value", aggfunc="last")
    latest_by_fut = latest_by_fut.loc[(latest_by_fut[["Sales", "Purchase", "OI"]].sum(axis=1) > 0)]
    latest_by_fut = latest_by_fut.loc[sorted(latest_by_fut.index, key=fut_expiry_date)]

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

# ── TAB: IMBALANCE HEATMAP ───────────────────────────────────────────────────
with tab_heatmap:
    st.markdown(
        "<div class='card-desc'>Net unfixed position (Sales − Purchases) by contract month over time. "
        "Green = more unfixed sales outstanding (latent futures-buying pressure to come as it gets fixed); "
        "red = more unfixed purchases outstanding (latent selling pressure). Rows are nearest-expiry first.</div>",
        unsafe_allow_html=True,
    )
    fsub = df[(df["Fut"] != "Totals") & (df["DateDT"].dt.date >= date_range[0]) & (df["DateDT"].dt.date <= date_range[1])]
    sales_p = fsub[fsub["Tag"] == "Sales"].pivot_table(index="Fut", columns="DateDT", values="Value", aggfunc="last")
    purch_p = fsub[fsub["Tag"] == "Purchase"].pivot_table(index="Fut", columns="DateDT", values="Value", aggfunc="last")
    net = sales_p.subtract(purch_p, fill_value=0)
    active_futs = [f for f in net.index if net.loc[f].abs().sum() > 0]
    active_futs = sorted(active_futs, key=fut_expiry_date, reverse=True)  # nearest expiry at bottom, reads top-down like a curve chain
    net = net.loc[active_futs]

    if net.empty:
        st.info("No contract-month data in the selected date range.")
    else:
        zmax = net.abs().to_numpy().max() or 1
        fig_hm = go.Figure(go.Heatmap(
            z=net.values, x=net.columns, y=net.index,
            colorscale=[[0, RED], [0.5, "#f5f0e6"], [1, GREEN]],
            zmid=0, zmin=-zmax, zmax=zmax,
            colorbar=dict(title="Net (Sales − Purch)"),
        ))
        chart_layout(fig_hm, height=max(320, 26 * len(net.index)))
        st.plotly_chart(fig_hm, width='stretch')

# ── TAB: SEASONALITY ─────────────────────────────────────────────────────────
with tab_season:
    st.markdown(
        "<div class='card-desc'>Every year plotted by week-of-year to see if there's a repeating seasonal pattern. "
        "Shaded band = 25th–75th percentile across all history; bold navy line = current year.</div>",
        unsafe_allow_html=True,
    )
    metric_options = {"Unfixed Sales": "Sales", "Unfixed Purchases": "Purchase", "Open Interest": "OI", "Net (Sales − Purchases)": "__net__"}
    metric_label = st.selectbox("Metric", list(metric_options.keys()))
    metric_key = metric_options[metric_label]

    season_df = totals_wide.copy()
    if metric_key == "__net__":
        season_df["__net__"] = season_df["Sales"] - season_df["Purchase"]
    season_df["woy"] = season_df.index.isocalendar().week.astype(int)
    season_df["yr"] = season_df.index.year

    band = season_df.groupby("woy")[metric_key].agg(p25=lambda s: s.quantile(0.25), p75=lambda s: s.quantile(0.75))
    current_year = season_df["yr"].max()

    fig_season = go.Figure()
    fig_season.add_trace(go.Scatter(x=band.index, y=band["p75"], line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig_season.add_trace(go.Scatter(x=band.index, y=band["p25"], fill="tonexty", fillcolor="rgba(31,138,156,0.15)",
                                     line=dict(width=0), name="25th–75th pct (history)"))
    for yr, grp in season_df.groupby("yr"):
        is_current = bool(yr == current_year)
        grp = grp.sort_values("woy")
        fig_season.add_trace(go.Scatter(
            x=grp["woy"], y=grp[metric_key], mode="lines", name=str(yr),
            line=dict(color=NAVY if is_current else "#c7cfe0", width=3 if is_current else 1),
            opacity=1 if is_current else 0.55, showlegend=is_current,
        ))
    chart_layout(fig_season, height=440, xaxis=dict(title="Week of year"), yaxis=dict(title=metric_label))
    st.plotly_chart(fig_season, width='stretch')

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

# ── TAB: EXPIRY WATCH (proof of concept) ─────────────────────────────────────
with tab_expiry:
    st.markdown(
        "<div class='card-desc'>Proof of concept: contract months nearest expiry, ranked by how large their "
        "unfixed (Sales − Purchases) imbalance is relative to Open Interest. Large residual imbalance close to "
        "expiry is the trading idea from earlier — it has to get fixed one way or another, which can mean forced "
        "futures buying or selling as the month rolls off. Expiry date shown is the contract month itself "
        "(1st of month), not the real notice/expiry day - a rough proxy, not exact.</div>",
        unsafe_allow_html=True,
    )
    n_months = st.slider("How many nearest-expiry months to watch", 2, 10, 6)

    latest_all = df[df["DateDT"] == totals_wide.index[-1]]
    snap = latest_all[latest_all["Fut"] != "Totals"].pivot_table(index="Fut", columns="Tag", values="Value", aggfunc="last")
    snap = snap.loc[(snap[["Sales", "Purchase", "OI"]].sum(axis=1) > 0)]
    snap = snap.loc[[f for f in snap.index if fut_expiry_date(f) >= pd.Timestamp(latest_date)]]
    snap = snap.loc[sorted(snap.index, key=fut_expiry_date)].head(n_months)

    watch = pd.DataFrame({
        "Contract month": snap.index,
        "~Days to expiry": [(fut_expiry_date(f) - pd.Timestamp(latest_date)).days for f in snap.index],
        "Sales": snap["Sales"].values,
        "Purchase": snap["Purchase"].values,
        "OI": snap["OI"].values,
        "Net (Sales - Purch)": (snap["Sales"] - snap["Purchase"]).values,
    })
    watch["Imbalance % of OI"] = (watch["Net (Sales - Purch)"] / watch["OI"].replace(0, pd.NA) * 100).round(1)
    watch["Flag"] = watch["Imbalance % of OI"].abs().apply(lambda x: "High" if pd.notna(x) and x >= 30 else "")

    st.dataframe(
        watch.set_index("Contract month").style
            .format({"Sales": "{:,.0f}", "Purchase": "{:,.0f}", "OI": "{:,.0f}",
                      "Net (Sales - Purch)": "{:+,.0f}", "Imbalance % of OI": "{:+.1f}%"})
            .apply(lambda s: ["background-color: rgba(233,90,90,0.12)" if v == "High" else "" for v in watch["Flag"]], subset=["Flag"]),
        width='stretch',
    )
    st.caption("\"High\" flag = |net imbalance| >= 30% of that month's Open Interest. Threshold is a starting guess, not a backtested number - tune it once there's a view on what's actually predictive.")

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
