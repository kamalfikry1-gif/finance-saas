"""
tests/conftest.py — Shared fixtures for pytest.

Strategy: we mock DatabaseManager instead of hitting a real Postgres.
This keeps tests fast and doesn't require a running DB. The mock
simulates the _ConnProxy behavior (execute, fetchone, fetchall).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, List, Optional, Tuple
from unittest.mock import MagicMock

import pytest

# Ensure the project root is on sys.path so `import audit`, `import logic_sqlite` work
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class FakeCursor:
    """Mimics the _ConnProxy cursor: supports execute → fetchone / fetchall."""

    def __init__(self, rows: List[Tuple] | None = None):
        self._rows = rows or []

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class FakeConnection:
    """
    Minimal in-memory connection that records executed SQL + params
    and returns canned results. Used to isolate business logic from DB.

    `queue_rows` pushes one result set onto a FIFO queue — each execute
    that asks for rows consumes the next entry. Execute calls that don't
    read rows don't consume the queue.
    """

    def __init__(self):
        self.calls: List[Tuple[str, Optional[Tuple]]] = []
        self._row_queue: List[List[Tuple]] = []

    def queue_rows(self, rows: List[Tuple]):
        """Append one result set to the end of the queue."""
        self._row_queue.append(list(rows))

    def execute(self, sql: str, params: Optional[Any] = None):
        self.calls.append((sql.strip(), params))
        rows = self._row_queue.pop(0) if self._row_queue else []
        return FakeCursor(rows)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeDB:
    """Stand-in for DatabaseManager. Exposes .connexion() as a context manager."""

    def __init__(self):
        self.conn = FakeConnection()

    def connexion(self):
        return self.conn

    # Methods the Trieur and audit layer call on the DB directly
    def enregistrer_mot_cle_inconnu(self, mot_cle, sens, cat, scat, user_id):
        self.conn.calls.append(("enregistrer_mot_cle_inconnu",
                                (mot_cle, sens, cat, scat, user_id)))


@pytest.fixture
def fake_db() -> FakeDB:
    """Fresh FakeDB per test."""
    return FakeDB()


@pytest.fixture
def mock_audit():
    """Bare-bones mock of AuditMiddleware for view-level tests."""
    audit = MagicMock()
    audit.user_id = 1
    return audit
