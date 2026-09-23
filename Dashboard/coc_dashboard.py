import sys
import warnings
from datetime import datetime, timedelta
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
GREY = "#8a94a8"

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

/* Pill / segmented-control tabs */
.stTabs [data-baseweb="tab-list"] {
    background: #eef0f6;
    padding: 4px;
    border-radius: 999px;
    gap: 4px;
    display: inline-flex;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    color: #5a6688 !important;
    border-radius: 999px !important;
    padding: 8px 20px !important;
    font-weight: 600;
    border: none !important;
}
.stTabs [aria-selected="true"] { background: #0a2463 !important; color: #ffffff !important; }
.stTabs [data-baseweb="tab-highlight"] { display: none !important; }
.stTabs [data-baseweb="tab-border"] { display: none !important; }

/* Radio as pill/segmented control too (date-range presets) */
div[role="radiogroup"] { background: #eef0f6; padding: 4px; border-radius: 999px; gap: 2px; display: inline-flex; flex-wrap: wrap; }
div[role="radiogroup"] label { background: transparent !important; border-radius: 999px !important; padding: 4px 12px !important; margin: 0 !important; }
div[role="radiogroup"] label[data-baseweb="radio"] > div:first-child { display: none; }
div[role="radiogroup"] label div[data-testid="stMarkdownContainer"] p { font-size: 12px !important; color: #5a6688; }
div[role="radiogroup"] label:has(input:checked) { background: #0a2463 !important; }
div[role="radiogroup"] label:has(input:checked) div[data-testid="stMarkdownContainer"] p { color: #ffffff !important; font-weight: 600; }

.stDataFrame { background: #ffffff; }
.card-desc { color: #5a6688; font-size: 0.82rem; margin-top: -6px; margin-bottom: 10px; }

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

/* Sidebar title (replaces the removed hero heading) */
.sb-title { font-family: 'Fraunces', Georgia, serif; font-size: 1.5rem; font-weight: 600; color: #0a2463; margin-bottom: 2px; }
.sb-caption { font-size: 11px; color: #7a86a8; margin-bottom: 16px; line-height: 1.4; }

/* Small filter-summary text in the sidebar */
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
    yaxis = dict(gridcolor="rgba(10,36,99,0.08)", color="#4a5578", hoverformat=".1f")
    xaxis.update(extra.pop("xaxis", {}))
    yaxis.update(extra.pop("yaxis", {}))
    if "yaxis2" in extra:
        y2 = dict(hoverformat=".1f")
        y2.update(extra["yaxis2"])
        extra["yaxis2"] = y2
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


def corr_annotation(fig, r, label="corr"):
    r2 = r ** 2 if pd.notna(r) else float("nan")
    text = f"{label} = {r:+.2f}  ·  R² = {r2:.2f}" if pd.notna(r) else "not enough data"
    fig.add_annotation(
        text=text, xref="paper", yref="paper", x=0.02, y=0.98, showarrow=False,
        font=dict(size=12, color=NAVY), bgcolor="rgba(255,255,255,0.85)",
        bordercolor="rgba(10,36,99,0.15)", borderwidth=1, borderpad=6,
    )


def square_scatter(x_series, y_series, xlabel, ylabel, latest_dt):
    """A strictly-square scatter with a correlation/R² annotation and the
    latest point highlighted, fixed 420x420 px (not stretched to container)."""
    both = pd.concat([x_series.rename("x"), y_series.rename("y")], axis=1).dropna()
    r = both["x"].corr(both["y"]) if len(both) > 2 else float("nan")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=both["x"], y=both["y"], mode="markers", marker=dict(color=TEAL, size=6, opacity=0.6),
        name="Weekly", hovertemplate="%{x:,.1f} / %{y:,.1f}<extra></extra>",
    ))
    if not both.empty:
        last = both.iloc[[-1]]
        fig.add_trace(go.Scatter(
            x=last["x"], y=last["y"], mode="markers",
            marker=dict(color=AMBER, size=13, line=dict(color="#fff", width=1.5)),
            name="Latest", hovertemplate=f"Latest ({latest_dt}): %{{x:,.1f}} / %{{y:,.1f}}<extra></extra>",
        ))
    chart_layout(
        fig, height=420, width=420, showlegend=False,
        xaxis=dict(title=xlabel, hoverformat=",.1f"), yaxis=dict(title=ylabel, hoverformat=",.1f"),
    )
    corr_annotation(fig, r)
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
    the price tabs can offer a leg selector (c1/c2/continuous)."""
    path = ROLLEX_CT_LIVE_PATH if ROLLEX_CT_LIVE_PATH.exists() else ROLLEX_CT_SNAPSHOT
    if not path.exists():
        return None
    rdf = pd.read_parquet(path)
    rdf.index = pd.to_datetime(rdf.index)
    return rdf


df = load_master()
totals = df[df["Fut"] == "Totals"].copy()
totals_wide = totals.pivot_table(index="DateDT", columns="Tag", values="Value", aggfunc="last").sort_index()
rollex_full = load_rollex_ct_full()

latest = totals_wide.iloc[-1]
latest_date = totals_wide.index[-1].date()

# ── SIDEBAR ──────────────────────────────────────────────────────────────────
min_d, max_d = totals_wide.index.min().date(), totals_wide.index.max().date()
with st.sidebar:
    st.markdown("<div class='sb-title'>Cotton On-Call</div>", unsafe_allow_html=True)
    st.markdown("<div class='sb-caption'>CFTC weekly report — unfixed cotton sales/purchases and open ICE futures interest.</div>", unsafe_allow_html=True)

    st.subheader("Filters")
    range_choice = st.radio("Range", ["3M", "6M", "12M", "3Y", "All", "Custom"], index=2, horizontal=True, label_visibility="collapsed")
    preset_days = {"3M": 91, "6M": 182, "12M": 365, "3Y": 365 * 3}
    if range_choice == "Custom":
        dc1, dc2 = st.columns(2)
        start_d = dc1.date_input("From", value=max(min_d, max_d - timedelta(weeks=52)), min_value=min_d, max_value=max_d)
        end_d = dc2.date_input("To", value=max_d, min_value=min_d, max_value=max_d)
        date_range = (start_d, end_d)
    elif range_choice == "All":
        date_range = (min_d, max_d)
    else:
        date_range = (max(min_d, max_d - timedelta(days=preset_days[range_choice])), max_d)

    st.divider()
    roll_window = st.selectbox(
        "Rolling average",
        options=[1, 4, 8, 13, 26],
        index=0,
        format_func=lambda w: "Raw" if w == 1 else f"{w}-week avg",
        help="Applies to every chart on this page.",
    )
    show_october = st.toggle("Show October contracts", value=False, help="October cotton is thinly traded - off by default.")

    st.divider()
    stat_rows = [
        ("On-Call as of", latest_date.strftime("%b %d, %Y"), f"{(datetime.today().date() - latest_date).days}d old"),
        ("Unfixed Sales", f"{latest['Sales']:,.0f}", f"{latest['S Change']:+,.0f} WoW"),
        ("Unfixed Purchases", f"{latest['Purchase']:,.0f}", f"{latest['P Change']:+,.0f} WoW"),
        ("Open Interest", f"{latest['OI']:,.0f}", f"{latest['OI Change']:+,.0f} WoW"),
    ]
    if rollex_full is not None and "rollex_px" in rollex_full.columns:
        px_series = rollex_full["rollex_px"].dropna()
        stat_rows.append(("CT price as of", px_series.index[-1].strftime("%b %d, %Y"), f"{px_series.iloc[-1]:.1f}"))
    sidebar_stats(stat_rows)

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


tab1, tab_season, tab2, tab_heatmap, tab3 = st.tabs([
    "Totals Over Time", "Seasonality", "By Contract Month", "Imbalance Heatmap", "Price Link (CT Rollex)",
])

LEG_OPTIONS = {"Rollex (continuous)": "rollex_px", "c1 (front month)": "c1", "c2 (second month)": "c2"}
if rollex_full is not None:
    LEG_OPTIONS = {k: v for k, v in LEG_OPTIONS.items() if v in rollex_full.columns}

# ── TAB 1: TOTALS OVER TIME ──────────────────────────────────────────────────
with tab1:
    st.markdown("<div class='card-desc'>Sales, purchases, open interest and price by week.</div>", unsafe_allow_html=True)
    leg_label_t1 = st.selectbox("Price leg (right axis)", list(LEG_OPTIONS.keys()), key="t1_leg") if rollex_full is not None else None

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=tv.index, y=tv["Sales"], name="Unfixed Sales", line=dict(color=RED, width=2)))
    fig.add_trace(go.Scatter(x=tv.index, y=tv["Purchase"], name="Unfixed Purchases", line=dict(color=GREEN, width=2)))
    fig.add_trace(go.Scatter(x=tv.index, y=tv["OI"], name="Open Interest", line=dict(color="#000000", width=1.6, dash="dot"), visible="legendonly"))
    yaxis2 = dict(overlaying="y", side="right", gridcolor="rgba(0,0,0,0)", color="#4a5578")
    if leg_label_t1 is not None:
        px = smooth(rollex_full[LEG_OPTIONS[leg_label_t1]].reindex(tv.index), roll_window)
        fig.add_trace(go.Scatter(x=tv.index, y=px, name=f"CT price ({leg_label_t1})", line=dict(color=AMBER, width=2), yaxis="y2"))
        yaxis2["title"] = "Price (Right Axis)"
    chart_layout(fig, height=440, yaxis2=yaxis2)
    st.plotly_chart(fig, width='stretch')

    st.markdown("<div class='card-desc'>Week-over-week change.</div>", unsafe_allow_html=True)
    fig2 = go.Figure()
    fig2.add_trace(go.Bar(x=tv.index, y=tv["S Change"], name="S Change", marker_color=RED))
    fig2.add_trace(go.Bar(x=tv.index, y=tv["P Change"], name="P Change", marker_color=GREEN))
    fig2.add_trace(go.Bar(x=tv.index, y=tv["OI Change"], name="OI Change", marker_color=GREY, visible="legendonly"))
    chart_layout(fig2, height=340, barmode="group")
    st.plotly_chart(fig2, width='stretch')

    st.markdown("<div class='card-desc'>Unfixed Sales and Purchases as a % of Open Interest.</div>", unsafe_allow_html=True)
    fig_ratio = go.Figure()
    fig_ratio.add_trace(go.Scatter(x=tv.index, y=(tv["Sales"] / tv["OI"] * 100), name="Sales / OI %", line=dict(color=RED, width=2)))
    fig_ratio.add_trace(go.Scatter(x=tv.index, y=(tv["Purchase"] / tv["OI"] * 100), name="Purchases / OI %", line=dict(color=GREEN, width=2)))
    chart_layout(fig_ratio, height=320, yaxis=dict(title="%", hoverformat=".1f"))
    st.plotly_chart(fig_ratio, width='stretch')

# ── TAB: SEASONALITY ─────────────────────────────────────────────────────────
with tab_season:
    st.markdown("<div class='card-desc'>Weekly pattern by year. Bands = history range; current year bold, last year red.</div>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    metric_options = {"Unfixed Sales": "Sales", "Unfixed Purchases": "Purchase", "Open Interest": "OI", "Net (Sales − Purchases)": "__net__"}
    metric_label = c1.selectbox("Metric", list(metric_options.keys()))
    metric_key = metric_options[metric_label]
    fut_group_options = ["All", "December", "March", "May", "July", "October"]
    fut_group = c2.selectbox("Contract month group", fut_group_options, index=0)

    if fut_group == "All":
        season_src = totals_wide.copy()
    else:
        fsub = df[(df["Fut"] != "Totals") & (df["Fut"].str.startswith(fut_group))]
        season_src = fsub.pivot_table(index="DateDT", columns="Tag", values="Value", aggfunc="sum").sort_index()

    season_df = season_src.copy()
    if metric_key == "__net__":
        season_df["__net__"] = season_df.get("Sales", 0) - season_df.get("Purchase", 0)
    season_df[metric_key] = smooth(season_df[metric_key], roll_window)
    season_df["woy"] = season_df.index.isocalendar().week.astype(int)
    season_df["yr"] = season_df.index.year

    band = season_df.groupby("woy")[metric_key].agg(
        lo="min", p10=lambda s: s.quantile(0.10), p25=lambda s: s.quantile(0.25),
        avg="mean", p75=lambda s: s.quantile(0.75), p90=lambda s: s.quantile(0.90), hi="max",
    ).sort_index()

    current_year = season_df["yr"].max()
    last_year = current_year - 1

    fig_season = go.Figure()
    # nested bands, widest/lightest first so inner bands draw on top
    band_pairs = [("lo", "hi", "rgba(31,138,156,0.08)", "Min–Max"), ("p10", "p90", "rgba(31,138,156,0.16)", "10th–90th pct"), ("p25", "p75", "rgba(31,138,156,0.28)", "25th–75th pct")]
    for lo_col, hi_col, color, name in band_pairs:
        fig_season.add_trace(go.Scatter(x=band.index, y=band[hi_col], line=dict(width=0), showlegend=False, hoverinfo="skip"))
        fig_season.add_trace(go.Scatter(x=band.index, y=band[lo_col], fill="tonexty", fillcolor=color, line=dict(width=0), name=name))
    fig_season.add_trace(go.Scatter(x=band.index, y=band["avg"], mode="lines", name="Average", line=dict(color="#4a5578", width=1.5, dash="dot")))

    for yr, color, width, dash in [(last_year, RED, 2, None), (current_year, NAVY, 3, None)]:
        grp = season_df[season_df["yr"] == yr].sort_values("woy")
        if grp.empty:
            continue
        fig_season.add_trace(go.Scatter(x=grp["woy"], y=grp[metric_key], mode="lines", name=str(yr), line=dict(color=color, width=width, dash=dash)))

    chart_layout(fig_season, height=460, xaxis=dict(title="Week of year", hoverformat=".0f"), yaxis=dict(title=metric_label))
    st.plotly_chart(fig_season, width='stretch')

# ── TAB 2: BY CONTRACT MONTH ─────────────────────────────────────────────────
with tab2:
    st.markdown("<div class='card-desc'>Latest snapshot, active months first. Zero-value months hidden.</div>", unsafe_allow_html=True)
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
        st.markdown("<div class='card-desc'>History for selected month(s).</div>", unsafe_allow_html=True)
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
        "<div class='card-desc'>Net position (Sales − Purchases) by month. "
        "Green = more unfixed sales; red = more unfixed purchases.</div>",
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
        st.info("No data in this date range.")
    else:
        zmax = net.abs().to_numpy().max() or 1
        fig_hm = go.Figure(go.Heatmap(
            z=net.values, x=net.columns, y=net.index,
            colorscale=[[0, RED], [0.5, "#f5f0e6"], [1, GREEN]],
            zmid=0, zmin=-zmax, zmax=zmax, zhoverformat=".1f",
            colorbar=dict(title="Net"),
        ))
        chart_layout(fig_hm, height=max(320, 26 * len(net.index)))
        st.plotly_chart(fig_hm, width='stretch')

# ── TAB 3: PRICE LINK (CT ROLLEX) ────────────────────────────────────────────
with tab3:
    st.markdown("<div class='card-desc'>On-Call totals vs. CT price.</div>", unsafe_allow_html=True)
    if rollex_full is None:
        st.info("CT price data not available in this environment yet.")
    else:
        metric_choices = {"Sales": ("Sales", "S Change"), "Purchases": ("Purchase", "P Change"), "Open Interest": ("OI", "OI Change")}

        c1, c2 = st.columns(2)
        leg_label = c1.selectbox("Price leg", list(LEG_OPTIONS.keys()), key="t3_leg")
        metric_label2 = c2.selectbox("Correlate with", list(metric_choices.keys()), index=2)
        level_col, change_col = metric_choices[metric_label2]

        rollex = rollex_full[[LEG_OPTIONS[leg_label]]].rename(columns={LEG_OPTIONS[leg_label]: "CT"})
        merged = tv.join(rollex, how="inner")
        merged["CT"] = smooth(merged["CT"], roll_window)
        merged["px_change"] = merged["CT"].diff()

        fig5 = go.Figure()
        fig5.add_trace(go.Scatter(x=merged.index, y=merged["CT"], name=f"CT price ({leg_label})", line=dict(color=AMBER, width=2)))
        fig5.add_trace(go.Bar(x=merged.index, y=merged[change_col], name=f"{metric_label2} Change", marker_color=TEAL, yaxis="y2", opacity=0.6))
        chart_layout(fig5, height=400, yaxis2=dict(overlaying="y", side="right", gridcolor="rgba(0,0,0,0)", color="#4a5578", title=f"{metric_label2} Change (Right Axis)"))
        st.plotly_chart(fig5, width='stretch')

        st.markdown("<div class='card-desc'>Price vs. On-Call metrics, level and weekly change. All plots square.</div>", unsafe_allow_html=True)
        r1c1, r1c2 = st.columns(2)
        with r1c1:
            st.plotly_chart(square_scatter(merged["CT"], merged[level_col], "Price level", f"{metric_label2} level", latest_date))
        with r1c2:
            st.plotly_chart(square_scatter(merged["px_change"], merged[change_col], "Price change", f"{metric_label2} change", latest_date))

        r2c1, r2c2 = st.columns(2)
        with r2c1:
            st.plotly_chart(square_scatter(tv["Sales"], tv["Purchase"], "Unfixed Sales level", "Unfixed Purchases level", latest_date))
        with r2c2:
            st.plotly_chart(square_scatter(tv["S Change"], tv["P Change"], "Unfixed Sales change", "Unfixed Purchases change", latest_date))

        st.caption("Weekly change measured Friday-as-of-date to Friday-as-of-date.")
