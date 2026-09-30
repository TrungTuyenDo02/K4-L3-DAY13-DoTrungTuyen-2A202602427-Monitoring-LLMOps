"""Pure pandas aggregations for the 6-panel dashboard.

Everything is computed from ``data/logs.jsonl`` following the pseudocode
``query`` of each panel in ``config/dashboard.yaml``. Thresholds, units and the
time range are read from that contract instead of being duplicated here.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from app.metrics import percentile

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG_PATH = REPO_ROOT / "data" / "logs.jsonl"
DASHBOARD_CONFIG_PATH = REPO_ROOT / "config" / "dashboard.yaml"
SLO_CONFIG_PATH = REPO_ROOT / "config" / "slo.yaml"

LONG_COLUMNS = ["minute", "series", "value"]


# --------------------------------------------------------------------------- config
def load_contract(path: Path = DASHBOARD_CONFIG_PATH) -> dict[str, Any]:
    dashboard = yaml.safe_load(path.read_text(encoding="utf-8"))["dashboard"]
    dashboard["panels_by_id"] = {panel["id"]: panel for panel in dashboard["panels"]}
    return dashboard


def load_guardrails(path: Path = SLO_CONFIG_PATH) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")).get("guardrails", {})


def meets_threshold(value: float | None, threshold: dict[str, Any]) -> bool | None:
    """True/False against the panel threshold; None when there is no data."""
    if value is None or pd.isna(value):
        return None
    if threshold["operator"] == "lte":
        return value <= threshold["value"]
    return value >= threshold["value"]


# --------------------------------------------------------------------------- loading
def load_logs(path: Path = DEFAULT_LOG_PATH) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if not rows:
        return pd.DataFrame(
            {"ts": pd.Series(dtype="datetime64[ns, UTC]"), "event": pd.Series(dtype="object")}
        )
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce", format="ISO8601")
    return df.dropna(subset=["ts"]).sort_values("ts").reset_index(drop=True)


def filter_window(df: pd.DataFrame, end: datetime, minutes: int) -> pd.DataFrame:
    start = pd.Timestamp(end - timedelta(minutes=minutes))
    return df[(df["ts"] > start) & (df["ts"] <= pd.Timestamp(end))]


def _events(df: pd.DataFrame, name: str) -> pd.DataFrame:
    if df.empty or "event" not in df:
        return df.iloc[0:0]
    return df[df["event"] == name]


def _numbers(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df:
        return pd.Series(dtype="float64")
    return pd.to_numeric(df[column], errors="coerce").dropna()


def _minute(df: pd.DataFrame) -> pd.Series:
    return df["ts"].dt.floor("min")


# --------------------------------------------------------------------------- panels
def latency_summary(df: pd.DataFrame) -> dict[str, float | None]:
    resp = _events(df, "response_sent")
    latency = _numbers(resp, "latency_ms").tolist()
    ttft = _numbers(resp, "ttft_ms").tolist()
    if not latency:
        return {"p50": None, "p95": None, "p99": None, "ttft_p95": None, "count": 0}
    return {
        "p50": percentile(latency, 50),
        "p95": percentile(latency, 95),
        "p99": percentile(latency, 99),
        "ttft_p95": percentile(ttft, 95) if ttft else None,
        "count": len(latency),
    }


def latency_by_minute(df: pd.DataFrame) -> pd.DataFrame:
    resp = _events(df, "response_sent")
    rows = []
    for minute, group in resp.groupby(_minute(resp)):
        latency = _numbers(group, "latency_ms").tolist()
        ttft = _numbers(group, "ttft_ms").tolist()
        if latency:
            rows += [
                (minute, "P50", percentile(latency, 50)),
                (minute, "P95", percentile(latency, 95)),
                (minute, "P99", percentile(latency, 99)),
            ]
        if ttft:
            rows.append((minute, "TTFT P95", percentile(ttft, 95)))
    return pd.DataFrame(rows, columns=LONG_COLUMNS)


def traffic_by_minute(df: pd.DataFrame) -> pd.DataFrame:
    received = _events(df, "request_received")
    counts = received.groupby(_minute(received)).size()
    return pd.DataFrame(
        {"minute": counts.index, "series": "Requests", "value": counts.to_numpy(dtype="float64")}
    )


def traffic_summary(df: pd.DataFrame, window_minutes: int) -> dict[str, float | None]:
    per_minute = traffic_by_minute(df)
    total = int(per_minute["value"].sum()) if not per_minute.empty else 0
    return {
        "count": total,
        "avg_rate_per_minute": total / window_minutes if window_minutes else None,
        "peak_rate_per_minute": float(per_minute["value"].max()) if total else None,
        # Threshold is evaluated on the latest minute that had traffic.
        "rate_per_minute": float(per_minute["value"].iloc[-1]) if total else None,
    }


def _tool_success_rate(df: pd.DataFrame) -> float | None:
    if "tool_success" not in df:
        return None
    flags = df["tool_success"].dropna()
    if flags.empty:
        return None
    return float((flags == True).sum() / len(flags) * 100)  # noqa: E712


def error_summary(df: pd.DataFrame) -> dict[str, Any]:
    received = len(_events(df, "request_received"))
    failed_df = _events(df, "request_failed")
    failed = len(failed_df)
    breakdown = (
        failed_df["error_type"].fillna("unknown").value_counts().to_dict()
        if failed and "error_type" in failed_df
        else {}
    )
    return {
        "received": received,
        "failed": failed,
        "error_rate_pct": failed / received * 100 if received else None,
        "error_breakdown": breakdown,
        "tool_success_rate_pct": _tool_success_rate(df),
    }


def errors_by_minute(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if df.empty:
        return pd.DataFrame(columns=LONG_COLUMNS)
    for minute, group in df.groupby(_minute(df)):
        received = len(_events(group, "request_received"))
        if received:
            failed = len(_events(group, "request_failed"))
            rows.append((minute, "Error rate", failed / received * 100))
        success = _tool_success_rate(group)
        if success is not None:
            rows.append((minute, "Retrieval success", success))
    return pd.DataFrame(rows, columns=LONG_COLUMNS)


def cost_summary(df: pd.DataFrame) -> dict[str, float | None]:
    cost = _numbers(_events(df, "response_sent"), "cost_usd")
    if cost.empty:
        return {"total": None, "avg_per_request": None}
    return {"total": float(cost.sum()), "avg_per_request": float(cost.mean())}


def cost_by_minute(df: pd.DataFrame) -> pd.DataFrame:
    resp = _events(df, "response_sent")
    if resp.empty or "cost_usd" not in resp:
        return pd.DataFrame(columns=["minute", "per_minute", "cumulative"])
    per_minute = pd.to_numeric(resp["cost_usd"], errors="coerce").groupby(_minute(resp)).sum()
    return pd.DataFrame(
        {
            "minute": per_minute.index,
            "per_minute": per_minute.to_numpy(),
            "cumulative": per_minute.cumsum().to_numpy(),
        }
    )


def token_summary(df: pd.DataFrame) -> dict[str, float | None]:
    resp = _events(df, "response_sent")
    tokens_in = _numbers(resp, "tokens_in")
    tokens_out = _numbers(resp, "tokens_out")
    if tokens_in.empty and tokens_out.empty:
        return {"tokens_in": None, "tokens_out": None, "avg_out_per_request": None}
    return {
        "tokens_in": float(tokens_in.sum()),
        "tokens_out": float(tokens_out.sum()),
        "avg_out_per_request": float(tokens_out.mean()) if not tokens_out.empty else None,
    }


def quality_summary(df: pd.DataFrame) -> dict[str, float | None]:
    quality = _numbers(_events(df, "response_sent"), "quality_score")
    return {"mean": float(quality.mean()) if not quality.empty else None, "count": len(quality)}


def quality_by_minute(df: pd.DataFrame) -> pd.DataFrame:
    resp = _events(df, "response_sent")
    if resp.empty or "quality_score" not in resp:
        return pd.DataFrame(columns=LONG_COLUMNS)
    mean = pd.to_numeric(resp["quality_score"], errors="coerce").groupby(_minute(resp)).mean()
    return pd.DataFrame(
        {"minute": mean.index, "series": "Quality mean", "value": mean.to_numpy()}
    )


def slowest_requests(df: pd.DataFrame, limit: int = 20) -> pd.DataFrame:
    """Rows for the investigation tab: pick a correlation_id, then open its trace."""
    columns = [
        "ts", "correlation_id", "event", "feature", "latency_ms", "ttft_ms",
        "tokens_out", "cost_usd", "quality_score", "error_type", "tool_success",
    ]
    rows = df[df["event"].isin(["response_sent", "request_failed"])] if "event" in df else df
    present = [c for c in columns if c in rows]
    ordered = rows[present].copy()
    if "latency_ms" in ordered:
        ordered = ordered.sort_values("latency_ms", ascending=False, na_position="first")
    return ordered.head(limit)
