"""
Worker Activity Tracker

Thread-safe registry of active thread pool tasks for the Rich progress display.
Tracks which workers are executing, what phase they're in, and per-task progress.
"""

from dataclasses import dataclass, field
from threading import RLock
from typing import Dict, List, Optional


@dataclass
class WorkerTask:
    """Snapshot of an active worker task."""
    task_id: str
    phase: str          # "SOQL" | "Download"
    object_name: str
    batch_idx: int
    status: str = ""
    progress_current: int = 0
    progress_total: int = 0
    detail: str = ""    # e.g. current filename for downloads


class WorkerActivityTracker:
    """Thread-safe registry of active tasks for the worker activity panel.

    Workers call register/update/unregister from their threads.
    The renderer calls get_active_tasks() on every render cycle (passive read).
    The keyboard listener calls toggle_panel() on keypress.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._tasks: Dict[str, WorkerTask] = {}
        self.show_panel: bool = False
        self.keyboard_available: bool = False

    def register_task(
        self,
        task_id: str,
        phase: str,
        object_name: str,
        batch_idx: int,
        total: int,
    ) -> None:
        """Register or re-register a task (idempotent).

        Called at the start of each task function. On retry,
        re-registers the same task_id cleanly.
        """
        with self._lock:
            self._tasks[task_id] = WorkerTask(
                task_id=task_id,
                phase=phase,
                object_name=object_name,
                batch_idx=batch_idx,
                status="starting",
                progress_current=0,
                progress_total=total,
            )

    def update_task(
        self,
        task_id: str,
        progress_current: int,
        status: str,
        detail: str = "",
    ) -> None:
        """Update progress for an active task.

        No-op if task_id is not registered (e.g. tracker is None guard
        was skipped by caller).
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is not None:
                task.progress_current = progress_current
                task.status = status
                task.detail = detail

    def unregister_task(self, task_id: str) -> None:
        """Remove a task from the active set.

        Called in the task function's finally block.
        No-op if task_id is not registered.
        """
        with self._lock:
            self._tasks.pop(task_id, None)

    def get_active_tasks(self) -> List[WorkerTask]:
        """Return a snapshot of all active tasks for the renderer.

        Returns a list of copies to avoid mutation during rendering.
        """
        with self._lock:
            return [
                WorkerTask(
                    task_id=t.task_id,
                    phase=t.phase,
                    object_name=t.object_name,
                    batch_idx=t.batch_idx,
                    status=t.status,
                    progress_current=t.progress_current,
                    progress_total=t.progress_total,
                    detail=t.detail,
                )
                for t in self._tasks.values()
            ]

    def toggle_panel(self) -> bool:
        """Toggle panel visibility. Returns new state."""
        with self._lock:
            self.show_panel = not self.show_panel
            return self.show_panel

    def clear_all_tasks(self) -> None:
        """Remove all tasks. Used between phase transitions."""
        with self._lock:
            self._tasks.clear()
