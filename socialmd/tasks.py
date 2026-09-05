"""Thread-safe in-memory task registry for background downloads."""

from __future__ import annotations

import threading
import time
import uuid
from contextlib import contextmanager
from typing import Optional

from .config import Config


class TaskManager:
    def __init__(self, max_parallel: int, retention: int) -> None:
        self._tasks: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._slots = threading.Semaphore(max_parallel)
        self._retention = retention

    def create(self) -> str:
        task_id = uuid.uuid4().hex
        with self._lock:
            self._prune()
            self._tasks[task_id] = {
                "status": "queued",
                "progress": 0,
                "speed": "",
                "eta": "",
                "created": time.time(),
            }
        return task_id

    def update(self, task_id: str, **fields) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is not None:
                task.update(fields)
                task["updated"] = time.time()

    def get(self, task_id: str) -> Optional[dict]:
        with self._lock:
            task = self._tasks.get(task_id)
            return dict(task) if task else None

    @contextmanager
    def slot(self):
        """Limit the number of simultaneous downloads."""
        self._slots.acquire()
        try:
            yield
        finally:
            self._slots.release()

    def _prune(self) -> None:
        """Drop finished tasks older than the retention window (lock held)."""
        cutoff = time.time() - self._retention
        for task_id in [
            tid for tid, t in self._tasks.items()
            if t.get("status") in ("done", "error") and t.get("updated", t["created"]) < cutoff
        ]:
            self._tasks.pop(task_id, None)


task_manager = TaskManager(Config.MAX_PARALLEL_DOWNLOADS, Config.TASK_RETENTION)