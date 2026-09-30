from __future__ import annotations

from contextlib import contextmanager

import pytest

from app import agent as agent_module
from app import incidents


class RecordedObservation:
    def __init__(self, name: str, as_type: str, kwargs: dict) -> None:
        self.name = name
        self.as_type = as_type
        self.start_kwargs = kwargs
        self.updates: list[dict] = []

    def update(self, **kwargs) -> None:
        self.updates.append(kwargs)


@pytest.fixture
def recorded(monkeypatch) -> list[RecordedObservation]:
    observations: list[RecordedObservation] = []

    @contextmanager
    def fake_start_observation(*, name: str, as_type: str = "span", **kwargs):
        obs = RecordedObservation(name, as_type, kwargs)
        observations.append(obs)
        yield obs

    monkeypatch.setattr(agent_module, "start_observation", fake_start_observation)
    return observations


def _run(message: str) -> agent_module.AgentResult:
    agent = agent_module.LabAgent()
    return agent_module.LabAgent.run.__wrapped__(
        agent,
        user_id="student-01",
        feature="qa",
        session_id="session-01",
        message=message,
        correlation_id="req-12345678",
    )


def test_run_opens_retrieval_then_generation(recorded) -> None:
    result = _run("What is the refund policy?")

    assert [(o.name, o.as_type) for o in recorded] == [
        ("retrieval", "retriever"),
        ("llm-generation", "generation"),
    ]
    generation = recorded[1]
    assert generation.start_kwargs["model"] == "claude-sonnet-4-5"
    assert generation.start_kwargs["metadata"]["prompt_name"]
    final = generation.updates[-1]
    assert final["usage_details"] == {"input": result.tokens_in, "output": result.tokens_out}
    assert final["cost_details"]["total"] == result.cost_usd
    assert final["completion_start_time"] is not None


def test_observations_only_carry_scrubbed_previews(recorded) -> None:
    _run("Refund for test@example.com, phone 0901234567?")

    blob = repr([(o.start_kwargs, o.updates) for o in recorded])
    assert "test@example.com" not in blob
    assert "0901234567" not in blob
    assert "REDACTED_EMAIL" in blob


def test_retrieval_failure_marks_span_as_error(recorded, monkeypatch) -> None:
    monkeypatch.setitem(incidents.STATE, "tool_fail", True)

    with pytest.raises(RuntimeError):
        _run("anything")

    retrieval = recorded[0]
    assert retrieval.updates[-1]["level"] == "ERROR"
    assert retrieval.updates[-1]["status_message"] == "RuntimeError"
    # The LLM is never called when retrieval fails.
    assert len(recorded) == 1
