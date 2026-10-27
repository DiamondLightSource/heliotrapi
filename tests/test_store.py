import uuid
from datetime import datetime, timedelta
from typing import Any, Literal

from heliotrapi.models import AnalysisResult
from heliotrapi.task_queue import QueueManager
from heliotrapi.task_queue.store import ResultStore


def make_result(
    status: Literal["error", "failed", "running", "completed"] = "completed",
    finished_at: datetime | None = None,
    result: Any = 10,
) -> AnalysisResult:
    return AnalysisResult(
        request_id=uuid.uuid4(),
        analysis_name="double",
        inputs={"number": 5},
        status=status,
        result=result,
        created_at=datetime.now(),
        finished_at=finished_at,
    )


def put(store: ResultStore, result: AnalysisResult) -> uuid.UUID:
    assert result.request_id is not None
    store[result.request_id] = result
    return result.request_id


def test_store_round_trips_result():
    store = ResultStore()
    result = make_result(finished_at=datetime.now(), result={"x": [1, 2, 3]})
    request_id = put(store, result)

    assert request_id in store
    assert store[request_id] == result
    assert list(store) == [request_id]


def test_store_overwrites_result():
    store = ResultStore()
    result = make_result(status="running")
    put(store, result)

    result.status = "completed"
    result.finished_at = datetime.now()
    request_id = put(store, result)

    assert len(store) == 1
    assert store[request_id].status == "completed"


def test_store_pop():
    store = ResultStore()
    result = make_result()
    request_id = put(store, result)

    assert store.pop(request_id) == result
    assert request_id not in store
    assert store.pop(request_id) is None


def test_store_latest_finished_ignores_running():
    store = ResultStore()
    older = make_result(finished_at=datetime.now() - timedelta(seconds=5))
    newer = make_result(finished_at=datetime.now())
    running = make_result(status="running")
    for r in (older, newer, running):
        put(store, r)

    assert store.latest_finished() == newer


def test_store_persists_to_file(tmp_path):
    db_path = tmp_path / "sub" / "results.db"
    result = make_result(finished_at=datetime.now())

    store = ResultStore(db_path)
    request_id = put(store, result)
    store.close()

    assert ResultStore(db_path)[request_id] == result


def test_queue_manager_fails_jobs_interrupted_by_restart(tmp_path):
    db_path = tmp_path / "results.db"
    running = make_result(status="running")

    store = ResultStore(db_path)
    request_id = put(store, running)
    store.close()

    qm = QueueManager(db_path=db_path)

    result = qm.results[request_id]
    assert result.status == "failed"
    assert result.finished_at is not None
