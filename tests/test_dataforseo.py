"""DataForSEO client: payload shape, chunking, poll outcomes, ledger idempotency."""

import io
import json
import urllib.request

import pytest

from aeo_research.dataforseo import (
    ACCEPTED_STATUS_CODE,
    DataForSeoError,
    Ledger,
    Submitted,
    TaskSpec,
    get_task,
    ledger_stats,
    post_tasks,
)


class FakeOpener:
    """Sequence of canned JSON responses; records every request."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests: list[urllib.request.Request] = []

    def __call__(self, req):
        self.requests.append(req)
        body = self.responses.pop(0)
        buf = io.BytesIO(json.dumps(body).encode())
        buf.__enter__ = lambda *a: buf
        buf.__exit__ = lambda *a: False
        return buf


def envelope(tasks):
    return {"status_code": 20000, "status_message": "Ok.", "tasks": tasks}


def accepted_task(task_id, cost=0.0024):
    return {"id": task_id, "status_code": ACCEPTED_STATUS_CODE, "cost": cost}


def test_task_spec_payload_matches_production_shape():
    payload = TaskSpec(keyword="best headphones", tag="aeo-exp002-w1").to_payload()
    assert payload == {
        "language_code": "en",
        "location_code": 2840,
        "keyword": "best headphones",
        "force_web_search": True,
        "device": "desktop",
        "os": "windows",
        "tag": "aeo-exp002-w1",
        "priority": 2,
    }


def test_post_tasks_chunks_at_100():
    specs = [TaskSpec(keyword=f"p{i}", tag="t") for i in range(150)]
    opener = FakeOpener(
        [
            envelope([accepted_task(f"id{i}") for i in range(100)]),
            envelope([accepted_task(f"id{i}") for i in range(100, 150)]),
        ]
    )
    out = post_tasks("key", specs, opener=opener)
    assert len(opener.requests) == 2
    assert len(out) == 150
    assert all(isinstance(s, Submitted) and s.accepted for s in out)
    first_body = json.loads(opener.requests[0].data.decode())
    assert len(first_body) == 100
    assert opener.requests[0].get_header("Authorization") == "Basic key"


def test_post_tasks_reports_rejections_without_raising():
    specs = [TaskSpec(keyword="ok", tag="t"), TaskSpec(keyword="bad", tag="t")]
    opener = FakeOpener(
        [
            envelope(
                [
                    accepted_task("id-ok"),
                    {"id": "", "status_code": 40501, "status_message": "Invalid Field"},
                ]
            )
        ]
    )
    out = post_tasks("key", specs, opener=opener)
    assert out[0].accepted and not out[1].accepted
    assert out[1].status_message == "Invalid Field"


def test_post_tasks_raises_on_envelope_error():
    opener = FakeOpener([{"status_code": 40100, "status_message": "Unauthorized."}])
    with pytest.raises(DataForSeoError):
        post_tasks("key", [TaskSpec(keyword="x", tag="t")], opener=opener)


def test_get_task_done_pending_failed():
    done = envelope(
        [
            {
                "id": "id1",
                "status_code": 20000,
                "cost": 0.0024,
                "result": [{"markdown": "hi", "fan_out_queries": ["a"], "sources": []}],
            }
        ]
    )
    pending = envelope([{"id": "id1", "status_code": 40602, "status_message": "Task in Queue."}])
    failed = envelope([{"id": "id1", "status_code": 40501, "status_message": "Invalid Field."}])

    opener = FakeOpener([done, pending, failed])
    d = get_task("key", "id1", opener=opener)
    assert d.state == "done" and d.result["markdown"] == "hi" and d.cost == 0.0024
    assert "task_get/advanced/id1" in opener.requests[0].full_url

    assert get_task("key", "id1", opener=opener).state == "pending"
    f = get_task("key", "id1", opener=opener)
    assert f.state == "failed" and f.status_code == 40501


def test_ledger_latest_record_wins_and_keys(tmp_path):
    led = Ledger(tmp_path / "ledger.jsonl")
    led.append(
        {"task_id": "a", "intent": "headphones", "item_id": "h001", "wave": 1,
         "status": "submitted", "cost": 0.0024}
    )
    led.append(
        {"task_id": "b", "intent": "headphones", "item_id": "h002", "wave": 1,
         "status": "submitted", "cost": 0.0024}
    )
    led.append(
        {"task_id": "a", "intent": "headphones", "item_id": "h001", "wave": 1,
         "status": "collected", "cost": 0.0024}
    )

    frame = led.frame()
    assert len(frame) == 2
    assert frame.set_index("task_id").loc["a", "status"] == "collected"

    assert led.submitted_keys() == {("headphones", "h001", 1), ("headphones", "h002", 1)}
    assert list(led.pending()["task_id"]) == ["b"]

    stats = ledger_stats(led)
    assert stats.total == 2
    assert stats.by_status == {"collected": 1, "submitted": 1}
    assert stats.cost == pytest.approx(0.0048)


def test_ledger_failed_tasks_are_resubmittable(tmp_path):
    led = Ledger(tmp_path / "ledger.jsonl")
    led.append(
        {"task_id": "a", "intent": "headphones", "item_id": "h001", "wave": 2,
         "status": "failed"}
    )
    # A failed (intent, item, wave) is NOT in submitted_keys -> submit skips nothing.
    assert led.submitted_keys() == set()
    assert led.pending().empty


def test_empty_ledger(tmp_path):
    led = Ledger(tmp_path / "missing.jsonl")
    assert led.frame().empty
    assert led.submitted_keys() == set()
    assert led.pending().empty
    assert ledger_stats(led).total == 0
