import sqlite3
import threading
import time
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from uuid import UUID

from heliotrapi.models import AnalysisResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS results (
    request_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    created_at REAL NOT NULL,
    finished_at REAL,
    data TEXT NOT NULL
)
"""


def _timestamp(dt: datetime | None) -> float | None:
    return None if dt is None else dt.timestamp()


class ResultStore:
    """Dict-like store of AnalysisResults, keyed by request_id, backed by sqlite.

    Each result is stored as its JSON dump, with the columns needed for
    querying (status and timestamps) pulled out alongside it.
    """

    def __init__(self, db_path: str | Path = ":memory:"):
        if str(db_path) != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        self.db_path = str(db_path)
        # the API and the workers can be on different threads (e.g. under
        # TestClient), so share one connection and serialise access to it
        self.conn = sqlite3.connect(
            self.db_path, isolation_level=None, check_same_thread=False
        )
        self.lock = threading.Lock()
        self._execute("PRAGMA journal_mode=WAL")
        self._execute(SCHEMA)

    def _execute(self, sql: str, params: tuple = ()) -> tuple[list, int]:
        """Run a statement, returning (rows, rowcount)."""
        with self.lock:
            cursor = self.conn.execute(sql, params)
            return cursor.fetchall(), cursor.rowcount

    def __setitem__(self, request_id: UUID, result: AnalysisResult) -> None:
        self._execute(
            "INSERT OR REPLACE INTO results VALUES (?, ?, ?, ?, ?)",
            (
                str(request_id),
                result.status,
                _timestamp(result.created_at),
                _timestamp(result.finished_at),
                result.model_dump_json(),
            ),
        )

    def __getitem__(self, request_id: UUID) -> AnalysisResult:
        rows, _ = self._execute(
            "SELECT data FROM results WHERE request_id = ?", (str(request_id),)
        )
        if not rows:
            raise KeyError(request_id)
        return AnalysisResult.model_validate_json(rows[0][0])

    def __contains__(self, request_id: object) -> bool:
        rows, _ = self._execute(
            "SELECT 1 FROM results WHERE request_id = ?", (str(request_id),)
        )
        return bool(rows)

    def __len__(self) -> int:
        rows, _ = self._execute("SELECT COUNT(*) FROM results")
        return rows[0][0]

    def __iter__(self) -> Iterator[UUID]:
        rows, _ = self._execute("SELECT request_id FROM results")
        for (request_id,) in rows:
            yield UUID(request_id)

    def values(self) -> list[AnalysisResult]:
        """All results, newest first."""
        rows, _ = self._execute("SELECT data FROM results ORDER BY created_at DESC")
        return [AnalysisResult.model_validate_json(data) for (data,) in rows]

    def pop(self, request_id: UUID, default=None) -> AnalysisResult | None:
        try:
            result = self[request_id]
        except KeyError:
            return default
        self._execute("DELETE FROM results WHERE request_id = ?", (str(request_id),))
        return result

    def latest_finished(self) -> AnalysisResult | None:
        rows, _ = self._execute(
            "SELECT data FROM results WHERE finished_at IS NOT NULL "
            "ORDER BY finished_at DESC LIMIT 1"
        )
        return AnalysisResult.model_validate_json(rows[0][0]) if rows else None

    def running(self) -> list[AnalysisResult]:
        rows, _ = self._execute("SELECT data FROM results WHERE status = 'running'")
        return [AnalysisResult.model_validate_json(data) for (data,) in rows]

    def delete_expired(self, ttl: float) -> int:
        """Delete results whose finished_at (or created_at) is older than ttl seconds.

        Returns the number of results deleted.
        """
        cutoff = time.time() - ttl
        _, deleted = self._execute(
            "DELETE FROM results WHERE COALESCE(finished_at, created_at) < ?",
            (cutoff,),
        )
        return deleted

    def close(self) -> None:
        with self.lock:
            self.conn.close()
