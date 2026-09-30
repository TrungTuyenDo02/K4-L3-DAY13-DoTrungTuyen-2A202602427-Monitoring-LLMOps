"""Streamlit dashboard: 6 panels from data/logs.jsonl, per config/dashboard.yaml.

Run from the repo root:  streamlit run dashboard/streamlit_app.py
(Not named app.py: that would shadow the `app` package when Streamlit puts
dashboard/ on sys.path.)
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
# Repo root first, so `app` / `dashboard` resolve to the packages, not to scripts.
if sys.path[:1] != [str(REPO_ROOT)]:
    sys.path.insert(0, str(REPO_ROOT))

import altair as alt  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from dashboard import data as d  # noqa: E402

LOCAL_TZ = "Asia/Ho_Chi_Minh"
THRESHOLD_COLOR = "#d03b3b"
MUTED_INK = "#898781"
# Categorical slots in fixed order; a series keeps its color in every panel.
SERIES_COLORS = {
    "P50": "#2a78d6",
    "P95": "#eb6834",
    "P99": "#1baf7a",
    "TTFT P95": "#eda100",
    "Requests": "#2a78d6",
    "Error rate": "#eb6834",
    "Retrieval success": "#2a78d6",
    "Cumulative cost": "#2a78d6",
    "tokens_in": "#2a78d6",
    "tokens_out": "#eb6834",
    "Quality mean": "#2a78d6",
}
UNIT_LABELS = {
    "ms": "ms",
    "requests_per_minute": "req/phút",
    "percent": "%",
    "usd": "USD",
    "tokens": "tokens",
    "score_0_to_1": "điểm 0–1",
}
OPERATORS = {"lte": "≤", "gte": "≥"}


# --------------------------------------------------------------------------- helpers
def fmt(value: float | None, pattern: str = "{:,.0f}") -> str:
    return "—" if value is None or pd.isna(value) else pattern.format(value)


def to_local(ts: pd.Series | pd.Timestamp):
    if isinstance(ts, pd.Series):
        return ts.dt.tz_convert(LOCAL_TZ).dt.tz_localize(None)
    return ts.tz_convert(LOCAL_TZ).tz_localize(None)


def localize_minutes(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    frame = frame.copy()
    frame["minute"] = to_local(pd.to_datetime(frame["minute"], utc=True))
    return frame


def threshold_text(panel: dict) -> str:
    t = panel["threshold"]
    return f"{t['aggregation']} {OPERATORS[t['operator']]} {t['value']:g} {UNIT_LABELS[panel['unit']]}"


def panel_header(index: int, panel: dict) -> None:
    st.subheader(f"{index}. {panel['title']}")
    st.caption(
        f"Đơn vị: **{UNIT_LABELS[panel['unit']]}** · Ngưỡng: **{threshold_text(panel)}** · "
        f"Nguồn: `{panel['source']}` ({', '.join(panel['events'])})"
    )


def status(ok: bool | None, detail: str) -> None:
    if ok is None:
        st.info(f"⚪ Chưa có dữ liệu trong cửa sổ — {detail}")
    elif ok:
        st.success(f"✅ Đạt ngưỡng — {detail}")
    else:
        st.error(f"❌ Vi phạm ngưỡng — {detail}")


def x_time(start: pd.Timestamp, end: pd.Timestamp) -> alt.X:
    return alt.X(
        "minute:T",
        title=f"Thời gian ({LOCAL_TZ})",
        scale=alt.Scale(domain=[start.isoformat(), end.isoformat()]),
        axis=alt.Axis(format="%H:%M", grid=False),
    )


def threshold_layer(value: float, label: str) -> alt.LayerChart:
    base = alt.Chart(pd.DataFrame({"y": [value], "label": [label]}))
    rule = base.mark_rule(color=THRESHOLD_COLOR, strokeDash=[6, 4], strokeWidth=2).encode(y="y:Q")
    text = base.mark_text(align="left", dx=4, dy=-7, color=MUTED_INK, fontSize=11).encode(
        y="y:Q", x=alt.value(0), text="label:N"
    )
    return rule + text


def color_scale(series: list[str]) -> alt.Color:
    return alt.Color(
        "series:N",
        scale=alt.Scale(domain=series, range=[SERIES_COLORS[s] for s in series]),
        # A single series is named by the panel title; legends only for >= 2 series.
        legend=alt.Legend(orient="top", title=None) if len(series) > 1 else None,
    )


def y_scale(values: pd.Series, *thresholds: float) -> alt.Scale:
    top = max([float(values.max()) if not values.empty else 0.0, *thresholds])
    return alt.Scale(domain=[0, top * 1.15 or 1])


def series_chart(
    frame: pd.DataFrame,
    series: list[str],
    x: alt.X,
    y_title: str,
    y_scale_: alt.Scale,
    value_format: str,
    rules: list[tuple[float, str]],
) -> alt.LayerChart:
    base = alt.Chart(frame).encode(
        x=x,
        y=alt.Y("value:Q", title=y_title, scale=y_scale_),
        color=color_scale(series),
        tooltip=[
            alt.Tooltip("minute:T", title="Phút", format="%H:%M"),
            alt.Tooltip("series:N", title="Series"),
            alt.Tooltip("value:Q", title=y_title, format=value_format),
        ],
    )
    layers = [base.mark_line(strokeWidth=2), base.mark_point(size=70, filled=True)]
    layers += [threshold_layer(value, label) for value, label in rules]
    return alt.layer(*layers).properties(height=240)


def show(chart: alt.TopLevelMixin) -> None:
    st.altair_chart(chart, width="stretch")


# --------------------------------------------------------------------------- panels
def render_latency(window, panel, x) -> None:
    summary = d.latency_summary(window)
    limit = panel["threshold"]["value"]
    status(
        d.meets_threshold(summary["p95"], panel["threshold"]),
        f"P95 = {fmt(summary['p95'])} ms (SLO {threshold_text(panel)})",
    )
    cols = st.columns(4)
    cols[0].metric("P50", f"{fmt(summary['p50'])} ms")
    cols[1].metric("P95", f"{fmt(summary['p95'])} ms")
    cols[2].metric("P99", f"{fmt(summary['p99'])} ms")
    cols[3].metric("TTFT P95", f"{fmt(summary['ttft_p95'])} ms")
    frame = localize_minutes(d.latency_by_minute(window))
    if frame.empty:
        return
    show(
        series_chart(
            frame, ["P50", "P95", "P99", "TTFT P95"], x, "Latency (ms)",
            y_scale(frame["value"], limit), ",.0f", [(limit, f"SLO P95 ≤ {limit:g} ms")],
        )
    )


def render_traffic(window, panel, x, minutes) -> None:
    summary = d.traffic_summary(window, minutes)
    limit = panel["threshold"]["value"]
    status(
        d.meets_threshold(summary["rate_per_minute"], panel["threshold"]),
        f"phút gần nhất có traffic: {fmt(summary['rate_per_minute'])} req/phút",
    )
    cols = st.columns(3)
    cols[0].metric(f"Tổng request ({minutes}′)", fmt(summary["count"]))
    cols[1].metric("TB req/phút", fmt(summary["avg_rate_per_minute"], "{:,.2f}"))
    cols[2].metric("Đỉnh req/phút", fmt(summary["peak_rate_per_minute"]))
    frame = localize_minutes(d.traffic_by_minute(window))
    if frame.empty:
        return
    bars = alt.Chart(frame).mark_bar(size=10, cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
        x=x,
        y=alt.Y("value:Q", title="Requests / phút", scale=y_scale(frame["value"], limit)),
        color=color_scale(["Requests"]),
        tooltip=[
            alt.Tooltip("minute:T", title="Phút", format="%H:%M"),
            alt.Tooltip("value:Q", title="Requests", format=",.0f"),
        ],
    )
    show(alt.layer(bars, threshold_layer(limit, f"≥ {limit:g} req/phút")).properties(height=240))


def render_errors(window, panel, x, guardrails) -> None:
    summary = d.error_summary(window)
    limit = panel["threshold"]["value"]
    retrieval_min = guardrails.get("retrieval_success_rate_pct_min")
    status(
        d.meets_threshold(summary["error_rate_pct"], panel["threshold"]),
        f"error rate = {fmt(summary['error_rate_pct'], '{:.2f}')}% ({threshold_text(panel)})",
    )
    cols = st.columns(3)
    cols[0].metric("Error rate", f"{fmt(summary['error_rate_pct'], '{:.2f}')} %")
    cols[1].metric("Failed / received", f"{summary['failed']} / {summary['received']}")
    cols[2].metric(
        "Retrieval success",
        f"{fmt(summary['tool_success_rate_pct'], '{:.1f}')} %",
        help=f"Guardrail trong config/slo.yaml: ≥ {retrieval_min}%",
    )
    frame = localize_minutes(d.errors_by_minute(window))
    if not frame.empty:
        rules = [(limit, f"Error rate ≤ {limit:g}%")]
        if retrieval_min is not None:
            rules.append((retrieval_min, f"Retrieval success ≥ {retrieval_min:g}%"))
        show(
            series_chart(
                frame, ["Error rate", "Retrieval success"], x, "Tỷ lệ (%)",
                alt.Scale(domain=[0, 105]), ".1f", rules,
            )
        )
    if summary["error_breakdown"]:
        st.caption("Breakdown theo `error_type`")
        st.dataframe(
            pd.DataFrame(
                {"error_type": list(summary["error_breakdown"]), "count": list(summary["error_breakdown"].values())}
            ),
            hide_index=True,
        )
    else:
        st.caption("Không có `request_failed` trong cửa sổ.")


def render_cost(window, panel, x) -> None:
    summary = d.cost_summary(window)
    limit = panel["threshold"]["value"]
    status(
        d.meets_threshold(summary["total"], panel["threshold"]),
        f"tổng = {fmt(summary['total'], '${:.4f}')} ({threshold_text(panel)})",
    )
    cols = st.columns(2)
    cols[0].metric("Tổng cost", fmt(summary["total"], "${:.4f}"))
    cols[1].metric("TB / request", fmt(summary["avg_per_request"], "${:.6f}"))
    frame = d.cost_by_minute(window)
    if frame.empty:
        return
    frame = localize_minutes(frame.assign(series="Cumulative cost", value=frame["cumulative"]))
    base = alt.Chart(frame).encode(
        x=x,
        y=alt.Y("value:Q", title="Cost cộng dồn (USD)", scale=y_scale(frame["value"], limit)),
        color=color_scale(["Cumulative cost"]),
        tooltip=[
            alt.Tooltip("minute:T", title="Phút", format="%H:%M"),
            alt.Tooltip("per_minute:Q", title="Cost trong phút (USD)", format="$.6f"),
            alt.Tooltip("value:Q", title="Cộng dồn (USD)", format="$.6f"),
        ],
    )
    show(
        alt.layer(
            base.mark_line(strokeWidth=2), base.mark_point(size=70, filled=True),
            threshold_layer(limit, f"Ngân sách ≤ ${limit:g}"),
        ).properties(height=240)
    )


def render_tokens(window, panel) -> None:
    summary = d.token_summary(window)
    limit = panel["threshold"]["value"]
    worst = max(summary["tokens_in"] or 0, summary["tokens_out"] or 0) if summary["tokens_in"] is not None else None
    status(
        d.meets_threshold(worst, panel["threshold"]),
        f"field lớn nhất = {fmt(worst)} tokens ({threshold_text(panel)})",
    )
    cols = st.columns(3)
    cols[0].metric("Σ tokens_in", fmt(summary["tokens_in"]))
    cols[1].metric("Σ tokens_out", fmt(summary["tokens_out"]))
    cols[2].metric("TB tokens_out / request", fmt(summary["avg_out_per_request"], "{:,.1f}"))
    if summary["tokens_in"] is None:
        return
    frame = pd.DataFrame(
        {"series": ["tokens_in", "tokens_out"], "value": [summary["tokens_in"], summary["tokens_out"]]}
    )
    base = alt.Chart(frame).encode(
        x=alt.X("series:N", title="Field", axis=alt.Axis(labelAngle=0)),
        y=alt.Y("value:Q", title="Tổng tokens", scale=y_scale(frame["value"], limit)),
    )
    bars = base.mark_bar(size=48, cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
        color=color_scale(["tokens_in", "tokens_out"]),
        tooltip=[alt.Tooltip("series:N", title="Field"), alt.Tooltip("value:Q", title="Tokens", format=",.0f")],
    )
    labels = base.mark_text(dy=-8, color=MUTED_INK).encode(text=alt.Text("value:Q", format=",.0f"))
    show(alt.layer(bars, labels, threshold_layer(limit, f"≤ {limit:,.0f} tokens")).properties(height=240))


def render_quality(window, panel, x) -> None:
    summary = d.quality_summary(window)
    limit = panel["threshold"]["value"]
    status(
        d.meets_threshold(summary["mean"], panel["threshold"]),
        f"mean = {fmt(summary['mean'], '{:.3f}')} ({threshold_text(panel)})",
    )
    cols = st.columns(2)
    cols[0].metric("Quality mean", fmt(summary["mean"], "{:.3f}"))
    cols[1].metric("Số response", fmt(summary["count"]))
    frame = localize_minutes(d.quality_by_minute(window))
    if frame.empty:
        return
    show(
        series_chart(
            frame, ["Quality mean"], x, "Quality (0–1)", alt.Scale(domain=[0, 1]), ".3f",
            [(limit, f"≥ {limit:g}")],
        )
    )


# --------------------------------------------------------------------------- page
st.set_page_config(page_title="Day13 Monitoring Dashboard", page_icon="📈", layout="wide")
contract = d.load_contract()
guardrails = d.load_guardrails()
panels = contract["panels_by_id"]

with st.sidebar:
    st.header("Cài đặt")
    log_input = st.text_input("File log (nguồn chuẩn)", "data/logs.jsonl")
    log_path = Path(log_input) if Path(log_input).is_absolute() else REPO_ROOT / log_input
    range_options = sorted({15, 30, 60, 180, 1440, contract["time_range_minutes"]})
    minutes = st.selectbox(
        "Time range (phút)", range_options, index=range_options.index(contract["time_range_minutes"])
    )
    auto_refresh = st.toggle(f"Tự refresh mỗi {contract['refresh_seconds']}s", value=True)
    st.caption("Contract: `config/dashboard.yaml` · Guardrail: `config/slo.yaml`")


@st.fragment(run_every=contract["refresh_seconds"] if auto_refresh else None)
def render_dashboard() -> None:
    now = datetime.now(timezone.utc)
    logs = d.load_logs(log_path)
    window = d.filter_window(logs, now, minutes)
    end_local = to_local(pd.Timestamp(now))
    start_local = end_local - pd.Timedelta(minutes=minutes)

    st.title(contract["title"])
    st.caption(
        f"🕒 Time range: **{start_local:%Y-%m-%d %H:%M} → {end_local:%H:%M}** ({LOCAL_TZ}, {minutes} phút) · "
        f"Refresh: **{contract['refresh_seconds']}s** {'(bật)' if auto_refresh else '(tắt)'} · "
        f"Nguồn: `{log_input}` · {len(window)}/{len(logs)} record trong cửa sổ · "
        f"Cập nhật lúc {to_local(pd.Timestamp(datetime.now(timezone.utc))):%H:%M:%S}"
    )

    tab_main, tab_investigate = st.tabs(["6 panel chính", "Điều tra: request bất thường"])
    x = x_time(start_local, end_local)
    with tab_main:
        row1 = st.columns(2)
        with row1[0].container(border=True):
            panel_header(1, panels["latency"])
            render_latency(window, panels["latency"], x)
        with row1[1].container(border=True):
            panel_header(2, panels["traffic"])
            render_traffic(window, panels["traffic"], x, minutes)
        row2 = st.columns(2)
        with row2[0].container(border=True):
            panel_header(3, panels["errors"])
            render_errors(window, panels["errors"], x, guardrails)
        with row2[1].container(border=True):
            panel_header(4, panels["cost"])
            render_cost(window, panels["cost"], x)
        row3 = st.columns(2)
        with row3[0].container(border=True):
            panel_header(5, panels["tokens"])
            render_tokens(window, panels["tokens"])
        with row3[1].container(border=True):
            panel_header(6, panels["quality"])
            render_quality(window, panels["quality"], x)

    with tab_investigate:
        st.markdown(
            "**Metrics → Logs → Traces**: xác định khoảng thời gian xấu ở tab 6 panel, "
            "chọn một `correlation_id` bên dưới, lọc dòng log đó trong `data/logs.jsonl`, "
            "rồi tìm trace trên Langfuse có metadata `correlation_id` trùng."
        )
        table = d.slowest_requests(window)
        if table.empty:
            st.info("Chưa có response/failed request trong cửa sổ.")
        else:
            table = table.assign(ts=to_local(table["ts"]).dt.strftime("%H:%M:%S"))
            st.dataframe(table, hide_index=True, width="stretch")


render_dashboard()
