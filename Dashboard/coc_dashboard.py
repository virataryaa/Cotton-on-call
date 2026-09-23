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
from coc_health import ROLLEX_CT_LIVE_PATH, ROLLEX_CT_SNAPSHOT, fut_active_sort_key  # noqa: E402

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


def smooth(series: pd.Series, window: int) -> pd.Series:
    if window <= 1:
        return series
    return series.rolling(window, min_periods=1).mean()


@st.cache_data(ttl=600)
def load_master() -> pd.DataFrame:
    df = pd.read_csv(MASTER_CSV)
    df["DateDT"] = pd.to_datetime(df["Date"], format="%m/%d/%Y")
    return df


@st.cache_data(ttl=600)
def load_rollex_ct_full():
    """Prefer the live desk-machine parquet (freshest); fall back to the repo
    copy the Automator ships, which is what makes this work on Streamlit
    Cloud (no access to the desk machine's filesystem). Keeps all columns so
    the Price Link tab can offer a leg selector (c1/c2/continuous)."""
    path = ROLLEX_CT_LIVE_PATH if ROLLEX_CT_LIVE_PATH.exists() else ROLLEX_CT_SNAPSHOT
    if not path.exists():
        return None
    rdf = pd.read_parquet(path)
    rdf.index = pd.to_datetime(rdf.index)
    return rdf


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

    st.divider()
    roll_window = st.selectbox(
        "Rolling average",
        options=[1, 4, 8, 13, 26],
        index=0,
        format_func=lambda w: "Raw (no smoothing)" if w == 1 else f"{w}-week rolling avg",
        help="Applies to every chart on this page: price, price change, Sales/Purchase/OI and their changes.",
    )
    show_october = st.toggle("Show October contracts", value=False, help="October cotton is thinly traded and mostly zero - off by default to cut clutter.")

    st.divider()
    sidebar_stats([
        ("As of", latest_date.strftime("%b %d, %Y"), f"{(datetime.today().date() - latest_date).days}d old"),
        ("Unfixed Sales", f"{latest['Sales']:,.0f}", f"{latest['S Change']:+,.0f} WoW"),
        ("Unfixed Purchases", f"{latest['Purchase']:,.0f}", f"{latest['P Change']:+,.0f} WoW"),
        ("Open Interest", f"{latest['OI']:,.0f}", f"{latest['OI Change']:+,.0f} WoW"),
    ])

mask = (totals_wide.index.date >= date_range[0]) & (totals_wide.index.date <= date_range[1])
tv = totals_wide.loc[mask].apply(lambda col: smooth(col, roll_window))


def active_fut_months(show_oct: bool) -> list[str]:
    """Contract months with non-zero Sales or Purchase in the latest report,
    October excluded unless show_oct, sorted active (still-trading) months
    first - nearest expiry first among those - then already-expired months
    after, most recently expired first."""
    latest_all = df[df["DateDT"] == totals_wide.index[-1]]
    snap = latest_all[latest_all["Fut"] != "Totals"].pivot_table(index="Fut", columns="Tag", values="Value", aggfunc="last")
    labels = snap[(snap["Sales"] > 0) | (snap["Purchase"] > 0)].index.tolist()
    if not show_oct:
        labels = [l for l in labels if not l.startswith("October")]
    return sorted(labels, key=lambda l: fut_active_sort_key(l, latest_date))


tab1, tab2, tab_heatmap, tab_season, tab3 = st.tabs([
    "Totals Over Time", "By Contract Month", "Imbalance Heatmap", "Seasonality", "Price Link (CT Rollex)",
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
    st.markdown(
        "<div class='card-desc'>Latest report snapshot, broken out by ICE futures contract month. "
        "Active months first (nearest expiry first), then already-expired months. "
        "Months with zero Sales and Purchase are hidden.</div>",
        unsafe_allow_html=True,
    )
    fut_months = active_fut_months(show_october)
    selected_fut = st.multiselect("Contract month(s) - history below", fut_months)

    latest_all = df[df["DateDT"] == totals_wide.index[-1]]
    latest_by_fut = latest_all[latest_all["Fut"] != "Totals"].pivot_table(index="Fut", columns="Tag", values="Value", aggfunc="last")
    latest_by_fut = latest_by_fut.loc[fut_months]

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
            fig4.add_trace(go.Scatter(x=sub["DateDT"], y=smooth(sub["OI"], roll_window), name=f"{fm} OI", mode="lines"))
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
    if not show_october:
        fsub = fsub[~fsub["Fut"].str.startswith("October")]
    sales_p = fsub[fsub["Tag"] == "Sales"].pivot_table(index="Fut", columns="DateDT", values="Value", aggfunc="last")
    purch_p = fsub[fsub["Tag"] == "Purchase"].pivot_table(index="Fut", columns="DateDT", values="Value", aggfunc="last")
    net = sales_p.subtract(purch_p, fill_value=0)
    net = net.apply(lambda row: smooth(row, roll_window), axis=1)
    active_futs = [f for f in net.index if net.loc[f].abs().sum() > 0]
    active_futs = sorted(active_futs, key=lambda l: fut_active_sort_key(l, latest_date), reverse=True)  # nearest expiry at bottom
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
    season_df[metric_key] = smooth(season_df[metric_key], roll_window)
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
        "<div class='card-desc'>Links weekly On-Call totals to a CT price leg "
        "(<code>rollex_CT.parquet</code>, refreshed daily by the Rollex pipeline) to see whether on-call "
        "positioning changes lead, lag, or track price moves.</div>",
        unsafe_allow_html=True,
    )
    rollex_full = load_rollex_ct_full()
    if rollex_full is None:
        st.info("CT Rollex price data isn't available in this environment yet — it ships as a snapshot refreshed by the Automator on the desk machine.")
    else:
        leg_options = {"Rollex (continuous)": "rollex_px", "c1 (front month)": "c1", "c2 (second month)": "c2"}
        leg_options = {k: v for k, v in leg_options.items() if v in rollex_full.columns}
        leg_label = st.selectbox("Price leg", list(leg_options.keys()))
        rollex = rollex_full[[leg_options[leg_label]]].rename(columns={leg_options[leg_label]: "CT"})

        merged = tv.join(rollex, how="inner")
        merged["CT"] = smooth(merged["CT"], roll_window)
        merged["px_change"] = merged["CT"].diff()
        merged = merged.dropna(subset=["px_change"])

        fig5 = go.Figure()
        fig5.add_trace(go.Scatter(x=merged.index, y=merged["CT"], name=f"CT price ({leg_label})", line=dict(color=AMBER, width=2)))
        fig5.add_trace(go.Bar(x=merged.index, y=merged["OI Change"], name="OI Change (On-Call)", marker_color=TEAL, yaxis="y2", opacity=0.6))
        chart_layout(fig5, height=400, yaxis2=dict(overlaying="y", side="right", gridcolor="rgba(0,0,0,0)", color="#4a5578", title="OI Change"))
        st.plotly_chart(fig5, width='stretch')

        st.markdown("<div class='card-desc'>Weekly OI Change vs. weekly price change.</div>", unsafe_allow_html=True)
        sq_l, sq_mid, sq_r = st.columns([1, 2, 1])
        with sq_mid:
            fig6 = go.Figure()
            fig6.add_trace(go.Scatter(x=merged["OI Change"], y=merged["px_change"], mode="markers", marker=dict(color=TEAL, size=7, opacity=0.7)))
            chart_layout(fig6, height=480, xaxis=dict(title="Weekly OI Change (On-Call)"), yaxis=dict(title="Weekly CT price change"))
            fig6.update_layout(width=480)
            st.plotly_chart(fig6)
        st.caption("Weekly change measured Friday-as-of-date to Friday-as-of-date (the report's own weekly cadence).")
