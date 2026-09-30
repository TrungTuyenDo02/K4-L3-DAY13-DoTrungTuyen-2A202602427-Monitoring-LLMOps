from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dashboard import data as d

NOW = datetime(2026, 9, 30, 3, 0, tzinfo=timezone.utc)


def _write_logs(tmp_path: Path) -> Path:
    rows = []
    for i in range(10):
        ts = (NOW - timedelta(minutes=i)).isoformat().replace("+00:00", "Z")
        cid = f"req-{i:08x}"
        rows.append({"ts": ts, "service": "api", "event": "request_received", "correlation_id": cid})
        if i == 0:
            rows.append(
                {"ts": ts, "service": "api", "event": "request_failed", "correlation_id": cid,
                 "error_type": "RuntimeError", "tool_name": "retrieval", "tool_success": False}
            )
            continue
        rows.append(
            {"ts": ts, "service": "api", "event": "response_sent", "correlation_id": cid,
             "latency_ms": i * 100, "ttft_ms": 50 + i, "tokens_in": 30, "tokens_out": 100,
             "cost_usd": 0.002, "quality_score": 0.9, "tool_name": "retrieval", "tool_success": True}
        )
    # An old request outside the 60-minute window must be ignored.
    old = (NOW - timedelta(hours=3)).isoformat().replace("+00:00", "Z")
    rows.append({"ts": old, "service": "api", "event": "request_received", "correlation_id": "req-deadbeef"})
    path = tmp_path / "logs.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\nnot-json\n", encoding="utf-8")
    return path


@pytest.fixture
def window(tmp_path: Path):
    return d.filter_window(d.load_logs(_write_logs(tmp_path)), NOW, 60)


def test_window_drops_old_records_and_bad_lines(window) -> None:
    assert "req-deadbeef" not in set(window["correlation_id"])
    assert len(d.load_logs(Path("does-not-exist.jsonl"))) == 0


def test_latency_percentiles_use_response_sent(window) -> None:
    summary = d.latency_summary(window)
    assert summary["count"] == 9
    assert summary["p50"] == 500
    assert summary["p99"] == 900
    assert summary["ttft_p95"] == 59


def test_error_rate_and_retrieval_success(window) -> None:
    summary = d.error_summary(window)
    assert summary["received"] == 10
    assert summary["failed"] == 1
    assert summary["error_rate_pct"] == pytest.approx(10.0)
    assert summary["error_breakdown"] == {"RuntimeError": 1}
    assert summary["tool_success_rate_pct"] == pytest.approx(90.0)


def test_cost_tokens_quality(window) -> None:
    assert d.cost_summary(window)["total"] == pytest.approx(0.018)
    tokens = d.token_summary(window)
    assert (tokens["tokens_in"], tokens["tokens_out"]) == (270, 900)
    assert d.quality_summary(window)["mean"] == pytest.approx(0.9)


def test_traffic_per_minute(window) -> None:
    summary = d.traffic_summary(window, 60)
    assert summary["count"] == 10
    assert summary["peak_rate_per_minute"] == 1


def test_thresholds_come_from_dashboard_contract() -> None:
    contract = d.load_contract()
    assert set(contract["panels_by_id"]) == {"latency", "traffic", "errors", "cost", "tokens", "quality"}
    latency = contract["panels_by_id"]["latency"]["threshold"]
    assert d.meets_threshold(2999, latency) is True
    assert d.meets_threshold(3001, latency) is False
    assert d.meets_threshold(None, latency) is None
