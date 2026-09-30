from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import httpx
import structlog

from app import logging_config
from app.main import app
from app.middleware import resolve_correlation_id

REQ_ID = re.compile(r"^req-[0-9a-f]{8}$")


def _post_chat(message: str, headers: dict[str, str] | None = None) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/chat",
                headers=headers or {},
                json={
                    "user_id": "student-01",
                    "session_id": "session-01",
                    "feature": "qa",
                    "message": message,
                },
            )

    return asyncio.run(send())


def _read_logs(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_resolve_correlation_id_reuses_valid_and_replaces_invalid() -> None:
    assert resolve_correlation_id("req-1a2b3c4d") == "req-1a2b3c4d"
    assert REQ_ID.match(resolve_correlation_id(None))
    assert REQ_ID.match(resolve_correlation_id("not-a-valid-id"))


def test_response_headers_echo_incoming_request_id(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(logging_config, "LOG_PATH", tmp_path / "logs.jsonl")

    response = _post_chat("Explain observability", headers={"x-request-id": "req-1a2b3c4d"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req-1a2b3c4d"
    assert response.json()["correlation_id"] == "req-1a2b3c4d"
    assert float(response.headers["x-response-time-ms"]) >= 0


def test_logs_are_enriched_and_ids_do_not_leak_between_requests(
    monkeypatch, tmp_path: Path
) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    first = _post_chat("Explain observability")
    second = _post_chat("How do I debug tail latency?")

    first_id = first.headers["x-request-id"]
    second_id = second.headers["x-request-id"]
    assert REQ_ID.match(first_id) and REQ_ID.match(second_id)
    assert first_id != second_id

    api_logs = [r for r in _read_logs(log_path) if r.get("service") == "api"]
    assert {r["correlation_id"] for r in api_logs} == {first_id, second_id}
    for record in api_logs:
        for field in ("user_id_hash", "session_id", "feature", "model", "env"):
            assert field in record, f"{field} missing in {record['event']}"
        assert record["user_id_hash"] != "student-01"


def test_raw_pii_never_reaches_log_file(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    _post_chat(
        "Email test@example.com, phone 0901234567, "
        "CCCD 012345678901, card 4111 1111 1111 1111"
    )

    raw = log_path.read_text(encoding="utf-8")
    for pii in ("test@example.com", "0901234567", "012345678901", "4111 1111 1111 1111"):
        assert pii not in raw
    assert "REDACTED_EMAIL" in raw


def test_scrub_processor_runs_before_file_writer_and_renderer() -> None:
    processors = structlog.get_config()["processors"]
    scrub_idx = processors.index(logging_config.scrub_event)
    writer_idx = next(
        i for i, p in enumerate(processors) if isinstance(p, logging_config.JsonlFileProcessor)
    )
    renderer_idx = next(
        i for i, p in enumerate(processors) if isinstance(p, structlog.processors.JSONRenderer)
    )
    assert scrub_idx < writer_idx < renderer_idx


def test_slow_requests_run_concurrently_and_keep_their_own_ids(
    monkeypatch, tmp_path: Path
) -> None:
    import time

    from app import agent as agent_module

    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    def slow_retrieve(message: str) -> list[str]:
        time.sleep(0.4)  # blocking, like the rag_slow practice scenario
        return ["doc"]

    monkeypatch.setattr(agent_module, "retrieve", slow_retrieve)

    async def send_many(n: int) -> list[httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {"user_id": "u", "session_id": "s", "feature": "qa", "message": "hi"}
            return await asyncio.gather(*(client.post("/chat", json=payload) for _ in range(n)))

    started = time.perf_counter()
    responses = asyncio.run(send_many(4))
    elapsed = time.perf_counter() - started

    # Sequential would be ~4 x (0.4 s retrieval + 0.15 s LLM) = 2.2 s.
    assert elapsed < 1.5, f"requests were serialized ({elapsed:.2f}s)"
    ids = {r.headers["x-request-id"] for r in responses}
    assert len(ids) == 4
    sent = [r for r in _read_logs(log_path) if r["event"] == "response_sent"]
    assert {r["correlation_id"] for r in sent} == ids
