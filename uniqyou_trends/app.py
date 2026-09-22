"""UniqYou — Fashion Trend Intelligence (Streamlit dashboard)."""
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
load_dotenv()

from data.keywords import ALL_KEYWORDS, FASHION_KEYWORDS, KEYWORD_CATEGORY  # noqa: E402
from pipeline.backtest import run_backtest  # noqa: E402
from pipeline.confidence import compute_confidence  # noqa: E402
from pipeline.ingest import (WIKI_ARTICLES, clear_signal_caches, fetch_editorial_mentions, fetch_google_trends,
                             fetch_wikipedia_attention, generate_synthetic_attention,  # noqa: E402
                             fetch_reddit_mentions, fetch_reddit_velocity,
                             generate_synthetic_signals, generate_synthetic_trends)
from pipeline.lifecycle import STAGE_EMOJI, Stage, classify_lifecycle  # noqa: E402
from pipeline.recommender import ACTION_COLOR, ACTION_DESCRIPTION, Action, recommend  # noqa: E402
from pipeline.velocity import score_all_keywords, split_by_volume  # noqa: E402

st.set_page_config(page_title="UniqYou — Fashion Trend Intelligence", page_icon="👗", layout="wide", initial_sidebar_state="collapsed")

GEO_CODES = {"India": "IN", "Worldwide": ""}
# Prototype evaluation targets (our own bar, not an industry benchmark)
TARGETS = {"mape": 15.0, "stage_accuracy": 0.60, "precision_at_test": 0.60}


# --------------------------------------------------------------------------- data loading
@st.cache_data(show_spinner=False, ttl=3600)
def load_trends(source: str, geo: str, force: bool = False):
    """Returns (trends_df, is_synthetic, note)."""
    if source.startswith("Live"):
        df = fetch_google_trends(ALL_KEYWORDS, geo=GEO_CODES[geo], force=force)
        if not df.empty and df.shape[1] >= len(ALL_KEYWORDS) // 2:
            return df, False, ""
        note = "Live Google Trends fetch failed or was rate-limited — fell back to synthetic demo data."
        return generate_synthetic_trends(ALL_KEYWORDS), True, note
    return generate_synthetic_trends(ALL_KEYWORDS), True, ""


@st.cache_data(show_spinner=False, ttl=3600)
def build_table(source: str, geo: str, force: bool = False):
    if force:
        clear_signal_caches()
    raw_trends, synthetic, note = load_trends(source, geo, force)
    trends, sparse = split_by_volume(raw_trends)  # zero-heavy keywords produce noise, not signal
    unfetched = [k for k in ALL_KEYWORDS if k not in raw_trends.columns] if not synthetic else []
    scores = score_all_keywords(trends)

    if synthetic:
        reddit_delta, editorial = generate_synthetic_signals(scores)
        wiki = generate_synthetic_attention(scores)
    else:
        wiki = fetch_wikipedia_attention(ALL_KEYWORDS)
        reddit_delta = fetch_reddit_velocity(ALL_KEYWORDS)
        reddit_mentions = fetch_reddit_mentions(ALL_KEYWORDS)
        editorial = fetch_editorial_mentions(ALL_KEYWORDS)
    reddit_ok, rss_ok = bool(reddit_delta), bool(editorial)
    reddit_mentions = reddit_mentions if not synthetic else {}

    rows = []
    for r in scores.itertuples():
        kw = r.keyword
        stage = classify_lifecycle(r.current_score, r.velocity, r.slope, r.streak, r.is_spike)
        conf = compute_confidence(r.velocity, reddit_delta.get(kw, 0.0), editorial.get(kw, 0), r.persistence,
                                  reddit_available=reddit_ok, rss_available=rss_ok,
                                  attention_delta=wiki.get(kw))
        rec = recommend(stage, conf["confidence_pct"], r.is_spike, r.streak)
        rows.append({**r._asdict(), "category": KEYWORD_CATEGORY.get(kw, ""), "stage": stage.value,
                     "reddit_delta": reddit_delta.get(kw), "reddit_mentions": reddit_mentions.get(kw),
                     "editorial": editorial.get(kw), "wiki_delta": wiki.get(kw), **conf, **{**rec, 'action': rec['action'].value}})
    table = pd.DataFrame(rows).drop(columns=["Index"]).sort_values("composite_score", ascending=False)
    return (table.reset_index(drop=True), trends, synthetic, note, reddit_ok, rss_ok, sparse, unfetched,
            datetime.now().strftime("%H:%M:%S"))


@st.cache_data(show_spinner=False)
def cached_backtest(trends: pd.DataFrame):
    return run_backtest(trends)


# --------------------------------------------------------------------------- design system
INK, MUTED, LINE, PLUM = "#1F1B24", "#6B6573", "#ECE6DC", "#5B2A86"
ACTION_STYLE = {  # (foreground, tint) tuned for a light background
    "TEST": ("#0B7F5D", "#DDF4EA"),
    "INCREASE": ("#6D3FD1", "#ECE6FB"),
    "WATCH": ("#A16207", "#FBF0D3"),
    "PASS": ("#C13B3B", "#FBE4E4"),
}
LOW_VOLUME_MAX = 20  # a keyword whose best week in the last 12 never passes 20/100 is too small to trust % moves
STAGE_TINT = {"Emerging": "#DDF4EA", "Rising": "#E2EEFB", "Peak": "#FBF0D3",
              "Declining": "#FBE4E4", "Dead": "#EAE7EE", "Spike": "#F9E3F1"}

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"], .stApp {{ font-family: 'Inter', system-ui, sans-serif; }}
.block-container {{ padding-top: 2.2rem; max-width: 1240px; }}
header[data-testid="stHeader"] {{ background: transparent; }}
#MainMenu, footer {{ visibility: hidden; }}
h1, h2, h3 {{ letter-spacing: -0.01em; }}

/* hero */
.hero {{ display:flex; justify-content:space-between; align-items:flex-end; gap:1rem; flex-wrap:wrap; margin-bottom:1.1rem; }}
.brand {{ font-family:'Fraunces', Georgia, serif; font-size:2.35rem; font-weight:600; color:{INK}; line-height:1.05; }}
.brand span {{ color:{PLUM}; font-style:italic; }}
.tagline {{ color:{MUTED}; font-size:0.98rem; margin-top:.35rem; }}
.pill {{ display:inline-flex; align-items:center; gap:.4rem; padding:.35rem .8rem; border-radius:999px;
        font-size:.78rem; font-weight:600; border:1px solid {LINE}; background:#fff; color:{INK}; }}
.pill .dot {{ width:8px; height:8px; border-radius:50%; }}

/* filter bar */
[data-testid="stHorizontalBlock"]:has(.filterbar-anchor) {{ background:#fff; border:1px solid {LINE};
        border-radius:16px; padding:.6rem .9rem; align-items:end; }}
label[data-testid="stWidgetLabel"] p {{ font-size:.72rem; font-weight:600; text-transform:uppercase;
        letter-spacing:.06em; color:{MUTED}; }}

/* KPI */
.kpis {{ display:grid; grid-template-columns:repeat(4, 1fr); gap:14px; margin:1.1rem 0 1.4rem; }}
@media (max-width:900px) {{ .kpis {{ grid-template-columns:repeat(2, 1fr); }} }}
.kpi {{ background:#fff; border:1px solid {LINE}; border-radius:16px; padding:16px 18px; position:relative; overflow:hidden; }}
.kpi::before {{ content:""; position:absolute; left:0; top:0; bottom:0; width:4px; background:var(--c); }}
.kpi .lbl {{ font-size:.72rem; font-weight:600; text-transform:uppercase; letter-spacing:.06em; color:{MUTED}; }}
.kpi .val {{ font-family:'Fraunces', serif; font-size:2.1rem; font-weight:600; color:{INK}; line-height:1.15; margin-top:4px; }}
.kpi .sub {{ font-size:.8rem; color:{MUTED}; margin-top:2px; }}

/* section headings */
.sec {{ display:flex; align-items:baseline; justify-content:space-between; gap:8px; flex-wrap:wrap; margin:.4rem 0 .6rem; }}
.sec h3 {{ font-family:'Fraunces', serif; font-size:1.45rem; font-weight:600; margin:0; padding:0; flex:1 1 auto; min-width:0; }}
.sec .hint {{ color:{MUTED}; font-size:.85rem; flex:1 1 auto; }}

/* trend cards */
[class*="st-key-card_"] {{ background:#fff; border:1px solid {LINE}; border-radius:18px; padding:18px 18px 12px;
        transition:box-shadow .18s, transform .18s, border-color .18s; gap:.35rem; }}
[class*="st-key-card_"]:hover {{ box-shadow:0 10px 28px rgba(60,30,90,.10); transform:translateY(-2px); border-color:#DCD2E6; }}
.card-top {{ display:flex; justify-content:space-between; align-items:flex-start; gap:8px; }}
.card-name {{ font-weight:600; font-size:1.05rem; color:{INK}; text-transform:capitalize; line-height:1.25; }}
.card-cat {{ font-size:.76rem; color:{MUTED}; margin-top:2px; text-transform:capitalize; }}
.badge {{ padding:3px 11px; border-radius:999px; font-size:.72rem; font-weight:700; letter-spacing:.04em; white-space:nowrap; }}
.rank {{ font-size:.7rem; font-weight:700; color:{MUTED}; letter-spacing:.06em; }}
.mom {{ display:flex; align-items:baseline; gap:8px; margin-top:8px; }}
.mom .num {{ font-family:'Fraunces', serif; font-size:2rem; font-weight:600; line-height:1; }}
.mom .cap {{ font-size:.75rem; color:{MUTED}; }}
.spark {{ width:100%; height:52px; display:block; margin:6px 0 4px; }}
.chips {{ display:flex; gap:6px; flex-wrap:wrap; margin:4px 0 8px; }}
.chip {{ font-size:.72rem; font-weight:500; padding:3px 9px; border-radius:8px; color:{INK}; }}
.conf-row {{ display:flex; justify-content:space-between; font-size:.74rem; color:{MUTED}; font-weight:500; margin-bottom:4px; }}
.conf-row b {{ color:{INK}; }}
.bar {{ height:7px; background:#F1ECE3; border-radius:99px; overflow:hidden; }}
.bar > div {{ height:100%; border-radius:99px; background:linear-gradient(90deg, #8B5CF6, {PLUM}); }}
[class*="st-key-card_"] button {{ border-radius:10px; border:1px solid {LINE}; background:#FAF7F2; font-weight:600; font-size:.82rem; }}
[class*="st-key-card_"] button:hover {{ border-color:{PLUM}; color:{PLUM}; }}

/* detail dialog */
.d-grid {{ display:grid; grid-template-columns:repeat(3, 1fr); gap:10px; margin:.6rem 0 1rem; }}
.d-cell {{ background:#FAF7F2; border-radius:12px; padding:10px 12px; }}
.d-cell .l {{ font-size:.68rem; font-weight:600; text-transform:uppercase; letter-spacing:.06em; color:{MUTED}; }}
.d-cell .v {{ font-size:1.05rem; font-weight:600; color:{INK}; margin-top:2px; }}
.why {{ background:#F4EFFA; border-left:4px solid {PLUM}; border-radius:10px; padding:12px 14px; font-size:.92rem; color:{INK}; }}

/* notes strip + backtest */
.note {{ background:#fff; border:1px solid {LINE}; border-radius:12px; padding:10px 14px; font-size:.84rem; color:{MUTED}; margin-bottom:8px; }}
.note b {{ color:{INK}; }}
.note.warn {{ background:#FFF9E8; border-color:#F3E2A9; }}
.note.err {{ background:#FDF0F0; border-color:#F3C5C5; }}
.trow {{ display:grid; grid-template-columns:2fr 1fr 1fr 60px; gap:8px; padding:11px 14px; border-bottom:1px solid {LINE}; font-size:.9rem; align-items:center; }}
.trow.h {{ font-size:.7rem; font-weight:700; text-transform:uppercase; letter-spacing:.06em; color:{MUTED}; }}
.ok {{ color:#0B7F5D; font-weight:700; }} .no {{ color:#C13B3B; font-weight:700; }}
.stTabs [data-baseweb="tab-list"] {{ gap:6px; border-bottom:1px solid {LINE}; }}
.stTabs [data-baseweb="tab"] {{ font-weight:600; padding:10px 16px; }}

/* action filter: wrap onto a second row instead of hiding options behind horizontal scroll */
div[role="radiogroup"][aria-label="Action"] {{ flex-wrap: wrap !important; overflow: visible !important; height: auto !important; }}
div[role="radiogroup"][aria-label="Action"] button {{ flex: 0 0 auto; }}
</style>
"""


# --------------------------------------------------------------------------- UI helpers
def is_low_volume(series: pd.Series) -> bool:
    return float(series.iloc[-12:].max()) < LOW_VOLUME_MAX


LOW_VOL_CHIP = ("<span class='chip' style='background:#FBE9D6;color:#9A4A0B;font-weight:600' "
                "title='Search interest stayed under 20/100 for 12 weeks, so % moves are small-number noise'>"
                "⚠ Low volume</span>")


def arrow(v) -> str:
    return "→" if v is None or pd.isna(v) or v == 0 else ("↑" if v > 0 else "↓")


def fmt_pct(v) -> str:
    return "n/a" if v is None or pd.isna(v) else f"{v:+.0f}%"


def action_badge(action: str) -> str:
    fg, bg = ACTION_STYLE[action]
    return f"<span class='badge' style='color:{fg};background:{bg}'>{action}</span>"


def spark_svg(series: pd.Series, color: str) -> str:
    vals = [float(v) for v in series.values]
    hi, lo = max(vals), min(vals)
    span = (hi - lo) or 1.0
    w, h, pad = 200, 52, 4
    pts = [(i * w / (len(vals) - 1), pad + (h - 2 * pad) * (1 - (v - lo) / span)) for i, v in enumerate(vals)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"0,{h} {line} {w},{h}"
    ex, ey = pts[-1]
    return (f"<svg class='spark' viewBox='0 0 {w} {h}' preserveAspectRatio='none'>"
            f"<polygon points='{area}' fill='{color}' opacity='0.12'/>"
            f"<polyline points='{line}' fill='none' stroke='{color}' stroke-width='2' "
            f"stroke-linejoin='round' stroke-linecap='round' vector-effect='non-scaling-stroke'/>"
            f"<circle cx='{ex:.1f}' cy='{ey:.1f}' r='3' fill='{color}'/></svg>")


def plot_layout(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(height=height, margin=dict(l=8, r=8, t=8, b=8), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter, sans-serif", color=INK),
                      legend=dict(orientation="h", y=1.12, x=0))
    fig.update_xaxes(gridcolor="#EFE9DF", zeroline=False)
    fig.update_yaxes(gridcolor="#EFE9DF", zeroline=False)
    return fig


def kpi(label: str, value, sub: str, color: str) -> str:
    return (f"<div class='kpi' style='--c:{color}'><div class='lbl'>{label}</div>"
            f"<div class='val'>{value}</div><div class='sub'>{sub}</div></div>")


def note(html: str, kind: str = "") -> None:
    st.markdown(f"<div class='note {kind}'>{html}</div>", unsafe_allow_html=True)


@st.dialog("Trend detail", width="large")
def detail_dialog(row, trends: pd.DataFrame, geo: str, synthetic: bool, reddit_ok: bool, rss_ok: bool):
    fg, _ = ACTION_STYLE[row.action]
    st.markdown(f"<div class='card-top'><div><div class='card-name' style='font-size:1.6rem;"
                f"font-family:Fraunces,serif'>{row.keyword}</div>"
                f"<div class='card-cat'>{row.category.replace('_', ' ')} · {geo}</div></div>"
                f"{action_badge(row.action)}</div>", unsafe_allow_html=True)
    st.caption(ACTION_DESCRIPTION[Action(row.action)])
    st.markdown(f"<div class='why'><b>Why this call</b><br>{row.reason}</div>", unsafe_allow_html=True)

    cells = [
        ("Google search momentum", f"{row.velocity:+.0f}% {arrow(row.velocity)}",
         "this week vs the average of the previous 4 weeks"),
        ("Reddit mentions", f"{fmt_pct(row.reddit_delta)} {arrow(row.reddit_delta)}" if reddit_ok else "unavailable",
         "last 2 weeks vs the 2 weeks before" if reddit_ok else "Reddit not connected"),
        ("Magazine articles", f"{int(row.editorial)} articles" if rss_ok else "unavailable",
         "mentioning it in Vogue, Elle, Bazaar + 5 more, last 14 days" if rss_ok else "feeds unreachable"),
        ("Wikipedia page views", f"{fmt_pct(row.wiki_delta)} {arrow(row.wiki_delta)}" if pd.notna(row.wiki_delta) else "no data",
         "last 7 days vs the 4 weeks before" if pd.notna(row.wiki_delta) else "no dedicated article, or too little traffic"),
        ("Sources agreeing", f"{row.sources_agreeing} of {row.sources_total}",
         "independent sources that also show it rising"),
        ("Rising streak", f"{row.streak} week{'s' if row.streak != 1 else ''}",
         "weeks in a row Google interest went up"),
    ]
    st.markdown("<div class='d-grid'>" + "".join(
        f"<div class='d-cell'><div class='l'>{l}</div><div class='v'>{v}</div>"
        f"<div style='font-size:.72rem;color:{MUTED};margin-top:2px'>{t}</div></div>" for l, v, t in cells) + "</div>",
        unsafe_allow_html=True)

    st.markdown(f"<div class='conf-row'><span>Confidence</span><b>{row.confidence_pct}%</b></div>"
                f"<div class='bar'><div style='width:{row.confidence_pct}%'></div></div>", unsafe_allow_html=True)
    st.markdown(f"<div style='margin-top:12px'><span class='chip' style='background:{STAGE_TINT[row.stage]}'>"
                f"{STAGE_EMOJI[Stage(row.stage)]} {row.stage}</span> "
                f"{LOW_VOL_CHIP if is_low_volume(trends[row.keyword]) else ''}</div>", unsafe_allow_html=True)
    if is_low_volume(trends[row.keyword]):
        note(f"<b>Low volume.</b> This keyword's search interest never passed {LOW_VOLUME_MAX} out of 100 in the last "
             "12 weeks. A jump from 4 to 7 shows up as +75%, so treat the momentum figure as noise, not a trend.", "warn")

    s = trends[row.keyword].iloc[-26:]
    fig = go.Figure(go.Scatter(x=s.index, y=s.values, mode="lines", line=dict(color=fg, width=2.5, shape="spline"),
                               fill="tozeroy", fillcolor="rgba(91,42,134,0.08)",
                               hovertemplate="%{x|%b %d}: %{y:.0f}<extra></extra>"))
    plot_layout(fig, 240).update_yaxes(range=[0, 105])
    st.markdown("<div class='d-cell' style='margin-top:14px'><div class='l'>Google search interest · last 26 weeks</div></div>",
                unsafe_allow_html=True)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.caption("**How to read this:** each point is one week of Google search interest for this keyword, scaled "
               "0–100. 100 = its busiest week in the past 12 months, 50 = half as busy, 0 = almost no searches. "
               "It shows the shape of the trend, not the number of searches. A curve climbing at the right edge "
               "means interest is building now.")
    if synthetic:
        note("<b>Demo data.</b> Every signal here is synthetic and not validated against real UniqYou data.", "warn")


def trend_card(row, rank: int, trends: pd.DataFrame, ctx: dict):
    fg, _ = ACTION_STYLE[row.action]
    up = row.velocity >= 0
    mom_color = "#0B7F5D" if up else "#C13B3B"
    with st.container(key=f"card_{rank}_{row.keyword}"):
        st.markdown(
            f"<div class='card-top'><div><div class='rank'>#{rank}</div>"
            f"<div class='card-name'>{row.keyword}</div>"
            f"<div class='card-cat'>{row.category.replace('_', ' ')}</div></div>{action_badge(row.action)}</div>"
            f"<div class='mom'><span class='num' style='color:{mom_color}'>{row.velocity:+.0f}%</span>"
            f"<span class='cap'>{arrow(row.velocity)} vs prior 4 wks</span></div>"
            f"{spark_svg(trends[row.keyword].iloc[-12:], fg)}"
            f"<div class='chips'><span class='chip' style='background:{STAGE_TINT[row.stage]}'>"
            f"{STAGE_EMOJI[Stage(row.stage)]} {row.stage}</span>"
            f"<span class='chip' style='background:#F1ECE3'>{row.sources_agreeing}/{row.sources_total} sources</span>"
            f"<span class='chip' style='background:#F1ECE3'>{row.streak}w streak</span>"
            f"{LOW_VOL_CHIP if is_low_volume(trends[row.keyword]) else ''}</div>"
            f"<div class='conf-row'><span>Confidence</span><b>{row.confidence_pct}%</b></div>"
            f"<div class='bar'><div style='width:{row.confidence_pct}%'></div></div>"
            f"<div style='height:14px'></div>",
            unsafe_allow_html=True)
        if st.button("View details", key=f"btn_{rank}_{row.keyword}", use_container_width=True):
            detail_dialog(row, trends, ctx["geo"], ctx["synthetic"], ctx["reddit_ok"], ctx["rss_ok"])


# --------------------------------------------------------------------------- page
st.markdown(CSS, unsafe_allow_html=True)
hero_slot = st.container()

f1, f2, f3, f4 = st.columns([1.5, 1.1, 1.6, 0.8], vertical_alignment="bottom")
with f1:
    st.markdown("<div class='filterbar-anchor'></div>", unsafe_allow_html=True)
    source = st.segmented_control("Data source", ["Demo (Synthetic)", "Live (Google Trends)"],
                                  default="Demo (Synthetic)", format_func=lambda s: s.split(" ")[0],
                                  selection_mode="single") or "Demo (Synthetic)"
with f2:
    geo = st.selectbox("Region", list(GEO_CODES))
with f3:
    cat_labels = [c.replace("_", " ").title() for c in FASHION_KEYWORDS]
    category = st.selectbox("Category", ["All categories"] + cat_labels)
with f4:
    refresh = st.button("↻ Refresh", use_container_width=True,
                        help="Re-fetch Google Trends, Reddit and editorial feeds and rebuild the table")
if refresh:
    st.cache_data.clear()
    st.session_state["force_refresh"] = True
    st.rerun()

spinner_msg = ("Fetching Google Trends (≈30s, rate-limited)…" if source.startswith("Live") else "Scoring trends…")
force = st.session_state.pop("force_refresh", False)
with st.spinner(spinner_msg):
    table, trends, synthetic, note_msg, reddit_ok, rss_ok, sparse, unfetched, updated_at = build_table(source, geo, force)
if force:
    st.toast(f"Refreshed at {updated_at}" + (" (demo data is deterministic, so values are unchanged)" if synthetic else ""),
             icon="🔄")

if category != "All categories":
    view = table[table["category"] == category.lower().replace(" ", "_")].reset_index(drop=True)
else:
    view = table

status_color, status_txt = ("#F59E0B", "Demo data") if synthetic else ("#10B981", "Live data")
hero_slot.markdown(
    f"<div class='hero'><div><div class='brand'>Uniq<span>You</span> Trend Radar</div>"
    f"<div class='tagline'>See what women's fashion is about to want — and what to do about it.</div></div>"
    f"<div class='pill'><span class='dot' style='background:{status_color}'></span>{status_txt} · updated {updated_at}</div></div>",
    unsafe_allow_html=True)

# one consolidated, quiet notes area instead of stacked banners
st.markdown("<div style='height:.9rem'></div>", unsafe_allow_html=True)
notes = []
if note_msg:
    notes.append(("err", note_msg))
if synthetic:
    notes.append(("warn", "<b>Demo mode.</b> Trend data is synthetic and illustrative. Live mode connects to Google "
                          "Trends, Wikipedia and editorial feeds."))
if unfetched:
    notes.append(("warn", f"Google Trends did not return {len(unfetched)} keyword(s) ({', '.join(unfetched)}). "
                          "Press Refresh to retry."))
if not synthetic and not reddit_ok:
    notes.append(("", f"Live signals: Google Trends, editorial feeds and Wikipedia ({len(WIKI_ARTICLES)} of "
                      f"{len(ALL_KEYWORDS)} keywords have an article). Reddit is optional and not configured."))
if not synthetic and not rss_ok:
    notes.append(("", "Editorial RSS is unavailable — confidence excludes it."))
if sparse:
    notes.append(("", f"{len(sparse)} keyword(s) excluded for low search volume: {', '.join(sparse)}."))
if notes:
    with st.expander(f"Data notes ({len(notes)})", expanded=any(k == "err" for k, _ in notes)):
        for kind, msg in notes:
            note(msg, kind)

tab_main, tab_explore, tab_bt = st.tabs(["Recommendations", "Trend Explorer", "Backtest"])

# --------------------------------------------------------------------------- tab 1
with tab_main:
    n_emerging = int((view["stage"] == "Emerging").sum())
    n_conf = int((view["confidence_pct"] >= 70).sum())
    n_spike = int(view["is_spike"].sum())
    avg_mom = f"{view['velocity'].mean():+.0f}%" if len(view) else "n/a"
    st.markdown("<div class='kpis'>"
                + kpi("Emerging trends", n_emerging, "early, low saturation", "#0B7F5D")
                + kpi("Avg momentum", avg_mom, f"across {len(view)} trends", PLUM)
                + kpi("High confidence", n_conf, "≥ 70% cross-source", "#6D3FD1")
                + kpi("Spike alerts", n_spike, "1-week jumps to verify", "#A16207")
                + "</div>", unsafe_allow_html=True)

    st.markdown("<div class='sec'><h3>This week's recommendations</h3>"
                "<span class='hint'>Ranked by composite trend score</span></div>", unsafe_allow_html=True)
    c1, c2 = st.columns([3, 1.2], vertical_alignment="bottom")
    with c1:
        counts = view["action"].value_counts()
        opts = ["All"] + [a.value for a in Action]
        act = st.segmented_control(
            "Action", opts, default="All", label_visibility="collapsed",
            format_func=lambda a: f"All · {len(view)}" if a == "All" else f"{a} · {int(counts.get(a, 0))}") or "All"
    with c2:
        sort_by = st.selectbox("Sort", ["Top ranked", "Highest momentum", "Highest confidence"],
                               label_visibility="collapsed")

    shown = view if act == "All" else view[view["action"] == act]
    if sort_by == "Highest momentum":
        shown = shown.sort_values("velocity", ascending=False)
    elif sort_by == "Highest confidence":
        shown = shown.sort_values("confidence_pct", ascending=False)

    if shown.empty:
        st.info("No trends match these filters.")
    else:
        if act != "All":
            st.caption(ACTION_DESCRIPTION[Action(act)])
        limit = st.session_state.get("limit", 9)
        ctx = dict(geo=geo, synthetic=synthetic, reddit_ok=reddit_ok, rss_ok=rss_ok)
        page = list(shown.head(limit).itertuples())
        for start in range(0, len(page), 3):
            cols = st.columns(3)
            for col, (i, row) in zip(cols, enumerate(page[start:start + 3], start=start)):
                with col:
                    trend_card(row, i + 1, trends, ctx)
        if len(shown) > limit:
            _, mid, _ = st.columns([1, 1, 1])
            if mid.button(f"Show more ({len(shown) - limit} remaining)", use_container_width=True):
                st.session_state["limit"] = limit + 9
                st.rerun()

# --------------------------------------------------------------------------- tab 2
with tab_explore:
    st.markdown("<div class='sec'><h3>Momentum vs confidence</h3>"
                "<span class='hint'>Top-right is where TEST / INCREASE calls live. High momentum with low confidence "
                "is usually a spike or single-source noise.</span></div>", unsafe_allow_html=True)
    fig = go.Figure()
    for action in Action:
        sub = view[view["action"] == action.value]
        fig.add_trace(go.Scatter(
            x=sub["velocity"].clip(upper=150), y=sub["confidence_pct"], mode="markers",
            name=action.value, text=sub["keyword"],
            marker=dict(size=13, color=ACTION_STYLE[action.value][0], opacity=0.85, line=dict(color="#fff", width=1.5)),
            hovertemplate="<b>%{text}</b><br>momentum %{x:.0f}%<br>confidence %{y}%<extra></extra>"))
    plot_layout(fig, 440).update_layout(xaxis_title="Momentum (%, clipped at 150)", yaxis_title="Confidence (%)")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    st.markdown("<div class='sec'><h3>Top 10 · 12-week history</h3></div>", unsafe_allow_html=True)
    top = list(view.head(10).itertuples())
    for start in range(0, len(top), 5):
        cols = st.columns(5)
        for col, r in zip(cols, top[start:start + 5]):
            fg, _ = ACTION_STYLE[r.action]
            with col:
                st.markdown(f"<div class='kpi' style='--c:{fg};padding:12px 14px'>"
                            f"<div class='card-name' style='font-size:.9rem'>{r.keyword}</div>"
                            f"<div class='card-cat'>{r.velocity:+.0f}% · {STAGE_EMOJI[Stage(r.stage)]} {r.stage}</div>"
                            f"{spark_svg(trends[r.keyword].iloc[-12:], fg)}</div>", unsafe_allow_html=True)

# --------------------------------------------------------------------------- tab 3
with tab_bt:
    st.markdown("<div class='sec'><h3>Backtest</h3><span class='hint'>Walk-forward on the loaded history</span></div>",
                unsafe_allow_html=True)
    if synthetic:
        note("<b>Synthetic data.</b> Patterns were generated with the shapes the model looks for, so these numbers "
             "demonstrate the harness, not real-world accuracy. Use Live data for a meaningful result.", "warn")
    try:
        bt = cached_backtest(trends)
    except ValueError as e:
        st.error(str(e))
        st.stop()

    st.caption(f"{bt['n_keywords']} keywords · first {bt['train_weeks']} weeks = warm-up (rule-based, nothing fitted) · "
               f"last {bt['test_weeks']} weeks = test origins · {bt['horizon']}-week look-ahead · Google Trends only.")
    prec = bt["precision_at_test"]
    lead = bt["avg_lead_time_weeks"]
    st.markdown("<div class='kpis'>"
                + kpi("MAE (pts)", f"{bt['mae']:.2f}", f"{bt['mae'] - bt['naive_mae']:+.2f} vs naive", PLUM)
                + kpi("MAPE", f"{bt['mape']:.1f}%", "slope-projected vs actual", "#6D3FD1")
                + kpi("Stage accuracy", f"{bt['stage_accuracy']:.0%}", "moved as stage implies", "#0B7F5D")
                + kpi("Precision @ TEST", "n/a" if pd.isna(prec) else f"{prec:.0%}",
                      f"{bt['n_test_calls']} calls · base rate {bt['base_rate_rise']:.0%}", "#A16207")
                + "</div>", unsafe_allow_html=True)
    st.caption(f"Avg lead time before peak: **{'n/a' if pd.isna(lead) else f'{lead:.1f} weeks'}** "
               f"({bt['n_peaks_flagged']} of {bt['n_peaks']} peaks flagged EMERGING first — indicative only). "
               f"{bt['n_predictions']} predictions total.")

    rows = [
        ("MAPE", f"≤ {TARGETS['mape']:.0f}%", f"{bt['mape']:.1f}%", bt["mape"] <= TARGETS["mape"]),
        ("Stage accuracy", f"≥ {TARGETS['stage_accuracy']:.0%}", f"{bt['stage_accuracy']:.0%}",
         bt["stage_accuracy"] >= TARGETS["stage_accuracy"]),
        ("Precision @ TEST", f"≥ {TARGETS['precision_at_test']:.0%}", "n/a" if pd.isna(prec) else f"{prec:.0%}",
         None if pd.isna(prec) else prec >= TARGETS["precision_at_test"]),
        ("MAE vs naive", "lower", f"{bt['mae']:.2f} vs {bt['naive_mae']:.2f}", bt["mae"] < bt["naive_mae"]),
    ]
    mark = lambda ok: "<span class='ok'>✓</span>" if ok else ("—" if ok is None else "<span class='no'>✗</span>")  # noqa: E731
    st.markdown("<div class='sec'><h3>Prototype targets</h3><span class='hint'>Our own bar — not industry benchmarks</span></div>",
                unsafe_allow_html=True)
    st.markdown("<div style='background:#fff;border:1px solid #ECE6DC;border-radius:16px;overflow:hidden'>"
                "<div class='trow h'><span>Metric</span><span>Target</span><span>Actual</span><span>Met</span></div>"
                + "".join(f"<div class='trow'><span>{m}</span><span>{t}</span><span><b>{a}</b></span><span>{mark(ok)}</span></div>"
                          for m, t, a, ok in rows) + "</div>", unsafe_allow_html=True)

    st.markdown("<div class='sec' style='margin-top:1.4rem'><h3>Accuracy by stage</h3>"
                "<span class='hint'>Correct = trend moved as the stage implies over 4 weeks</span></div>",
                unsafe_allow_html=True)
    bs = bt["by_stage"].assign(accuracy=lambda d: (d["accuracy"] * 100).round(0).astype(int))
    st.dataframe(bs.rename(columns={"stage": "Stage", "n": "Predictions", "accuracy": "Accuracy"}),
                 hide_index=True, use_container_width=True,
                 column_config={"Accuracy": st.column_config.ProgressColumn(
                     "Accuracy", min_value=0, max_value=100, format="%d%%")})

    st.markdown("<div class='sec' style='margin-top:1.4rem'><h3>Train / test split</h3></div>", unsafe_allow_html=True)
    kw_pick = st.selectbox("Keyword", list(trends.columns), key="bt_kw")
    s = trends[kw_pick]
    split_x = s.index[bt["train_weeks"]]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=s.index[:bt["train_weeks"]], y=s.iloc[:bt["train_weeks"]], name="Train / history",
                             line=dict(color="#A78BFA", width=2.5)))
    fig.add_trace(go.Scatter(x=s.index[bt["train_weeks"] - 1:], y=s.iloc[bt["train_weeks"] - 1:], name="Test",
                             line=dict(color=PLUM, width=2.5)))
    fig.add_vline(x=split_x.timestamp() * 1000, line_dash="dash", line_color="#9A93A6")
    plot_layout(fig, 300).update_layout(yaxis_title="Interest (0–100)")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with st.expander("Per-keyword breakdown"):
        st.dataframe(bt["results_df"].sort_values("mape"), hide_index=True, use_container_width=True)

st.markdown("<div style='text-align:center;color:#6B6573;font-size:.78rem;margin:2rem 0 .5rem'>"
            "TEST = small exposure to validate demand — the system doesn't know MOQ, lead times, margins or inventory. "
            "Momentum detection, not forecasting.</div>", unsafe_allow_html=True)
