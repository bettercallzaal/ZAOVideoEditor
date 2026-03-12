"""Background task manager. Runs long operations in threads so they
survive frontend disconnects. Frontend polls for status."""

import threading
import traceback
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TaskStatus:
    task_id: str
    project: str
    operation: str
    status: str = "pending"       # pending, running, complete, error
    progress: int = 0             # 0-100
    message: str = ""
    result: Optional[dict] = None
    error: Optional[str] = None
    started_at: float = 0
    finished_at: float = 0


_tasks: dict[str, TaskStatus] = {}
_lock = threading.Lock()
_counter = 0


def create_task(project: str, operation: str) -> str:
    global _counter
    with _lock:
        _counter += 1
        task_id = f"{operation}_{project}_{_counter}"
        _tasks[task_id] = TaskStatus(
            task_id=task_id,
            project=project,
            operation=operation,
            started_at=time.time(),
        )
    return task_id


def get_task(task_id: str) -> Optional[TaskStatus]:
    return _tasks.get(task_id)


def get_project_tasks(project: str) -> list[TaskStatus]:
    return [t for t in _tasks.values() if t.project == project]


def get_active_task(project: str, operation: str) -> Optional[TaskStatus]:
    """Get the most recent running/pending task for this project+operation."""
    candidates = [
        t for t in _tasks.values()
        if t.project == project and t.operation == operation
        and t.status in ("pending", "running")
    ]
    return candidates[-1] if candidates else None


def update_task(task_id: str, **kwargs):
    task = _tasks.get(task_id)
    if task:
        for k, v in kwargs.items():
            setattr(task, k, v)


def run_in_background(task_id: str, fn, *args, **kwargs):
    """Run fn in a background thread, updating task status."""
    def wrapper():
        task = _tasks.get(task_id)
        if not task:
            return
        task.status = "running"
        try:
            result = fn(task_id, *args, **kwargs)
            task.status = "complete"
            task.progress = 100
            task.result = result
            task.finished_at = time.time()
        except Exception as e:
            traceback.print_exc()
            task.status = "error"
            task.error = str(e)
            task.finished_at = time.time()

    thread = threading.Thread(target=wrapper, daemon=True)
    thread.start()


def task_to_dict(task: TaskStatus) -> dict:
    return {
        "task_id": task.task_id,
        "project": task.project,
        "operation": task.operation,
        "status": task.status,
        "progress": task.progress,
        "message": task.message,
        "result": task.result,
        "error": task.error,
        "elapsed": round(
            (task.finished_at or time.time()) - task.started_at, 1
        ) if task.started_at else 0,
    }
