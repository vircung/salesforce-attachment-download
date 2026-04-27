"""
Threading infrastructure for Salesforce attachments workflow.

This module provides a thread pool implementation with retry logic,
configuration management, and synchronous fallback mode.
"""

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, List, Optional

import concurrent.futures

from src.config_limits import Workers, QueryTimeout, Retry
from src.exceptions import SFAuthError

logger = logging.getLogger(__name__)


@dataclass
class ThreadPoolConfig:
    """Configuration for the workflow thread pool.

    Attributes:
        query_workers: Number of worker threads (Workers.MIN-Workers.MAX, default Workers.DEFAULT)
        sync_only: If True, run tasks synchronously without threading (default False)
        query_timeout: Timeout in seconds for individual tasks (default QueryTimeout.QUERY_TASK)
    """
    query_workers: int = Workers.DEFAULT
    sync_only: bool = False
    query_timeout: int = QueryTimeout.QUERY_TASK

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if not Workers.MIN <= self.query_workers <= Workers.MAX:
            logger.warning(
                f"query_workers {self.query_workers} out of range {Workers.MIN}-{Workers.MAX}, setting to {Workers.DEFAULT}"
            )
            self.query_workers = Workers.DEFAULT


@dataclass
class WorkerResult:
    """Result of a worker task execution.

    Attributes:
        task_id: Unique task identifier
        success: Whether the task succeeded
        result: Task result if successful (None otherwise)
        error: Exception if task failed (None otherwise)
        attempts: Number of execution attempts (1-3)
        duration_ms: Task duration in milliseconds
    """
    task_id: str
    success: bool
    result: Optional[Any] = None
    error: Optional[Exception] = None
    attempts: int = 1
    duration_ms: float = 0.0


class WorkflowThreadPool:
    """Thread pool for executing workflow tasks with retry logic.

    Supports both threaded and synchronous execution modes.
    """

    def __init__(self, config: ThreadPoolConfig) -> None:
        """Initialize the thread pool.

        Args:
            config: Thread pool configuration
        """
        self.config = config
        self.executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=config.query_workers
        )
        self.pending_futures: dict[str, concurrent.futures.Future] = {}
        self.results: dict[str, WorkerResult] = {}
        logger.info(
            f"ThreadPool initialized with workers={config.query_workers}"
        )

    def __enter__(self) -> "WorkflowThreadPool":
        """Enter context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context manager and shutdown pool."""
        self.shutdown()

    def submit_task(
        self,
        task_id: str,
        fn: Callable[..., Any],
        args: tuple,
        max_retries: int = Retry.MAX_RETRIES_THREAD,
    ) -> None:
        """Submit a task for execution.

        Args:
            task_id: Unique task identifier
            fn: Callable to execute
            args: Arguments to pass to the callable
            max_retries: Max retry attempts (MAX_RETRIES_THREAD=3 means 3 total attempts)
        """
        future = self.executor.submit(
            self._execute_with_retries, task_id, fn, args, max_retries
        )
        self.pending_futures[task_id] = future
        logger.debug(f"Submitted task {task_id}")

    def _execute_with_retries(
        self,
        task_id: str,
        fn: Callable[..., Any],
        args: tuple,
        max_retries: int,
    ) -> WorkerResult:
        """Execute a task with retry logic and exponential backoff.

        Args:
            task_id: Task identifier
            fn: Callable to execute
            args: Arguments for the callable
            max_retries: Maximum number of retry attempts

        Returns:
            WorkerResult with execution outcome
        """
        start_time = time.time()
        last_exception: Optional[Exception] = None

        for attempt in range(1, max_retries + 1):
            try:
                result = fn(*args)
                duration = (time.time() - start_time) * 1000
                logger.info(f"Task {task_id} succeeded on attempt {attempt}")
                return WorkerResult(
                    task_id=task_id,
                    success=True,
                    result=result,
                    attempts=attempt,
                    duration_ms=duration,
                )
            except Exception as e:
                last_exception = e
                logger.warning(f"Task {task_id} failed on attempt {attempt}: {e}")
                if attempt < max_retries and not isinstance(e, SFAuthError):
                    delay = Retry.DELAY_FIRST if attempt == 1 else Retry.DELAY_SUBSEQUENT
                    time.sleep(delay)
                    logger.info(f"Retrying task {task_id} after {delay}s delay")

        # All attempts failed
        duration = (time.time() - start_time) * 1000
        return WorkerResult(
            task_id=task_id,
            success=False,
            error=last_exception,
            attempts=max_retries,
            duration_ms=duration,
        )

    def wait_for_completion(self, phase_name: str, timeout: Optional[int] = None) -> List[WorkerResult]:
        """Wait for all pending tasks to complete.

        Args:
            phase_name: Name of the workflow phase for logging
            timeout: Per-task timeout in seconds. None = wait indefinitely.
                     Use None for long-running tasks like downloads.
                     Use config.query_timeout for short tasks like SOQL queries.

        Returns:
            List of WorkerResult objects for all tasks
        """
        for task_id, future in list(self.pending_futures.items()):
            try:
                worker_result = future.result(timeout=timeout)
                self.results[task_id] = worker_result
            except concurrent.futures.TimeoutError:
                logger.warning(f"Task {task_id} timed out after {timeout}s")
                self.results[task_id] = WorkerResult(
                    task_id=task_id,
                    success=False,
                    error=TimeoutError(f"Task timed out after {timeout}s"),
                    attempts=1,
                    duration_ms=(timeout or 0) * 1000,
                )
            except Exception as e:
                logger.warning(f"Task {task_id} failed: {e}")
                self.results[task_id] = WorkerResult(
                    task_id=task_id,
                    success=False,
                    error=e,
                    attempts=1,
                    duration_ms=0.0,
                )

        self.pending_futures.clear()
        logger.info(f"Phase '{phase_name}' completed")
        return self._collect_results()

    def clear_results(self) -> None:
        """Clear all stored results.
        
        Useful when reusing the thread pool across different phases
        to avoid mixing results from different operations.
        """
        self.results.clear()
        logger.debug("Cleared all thread pool results")

    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the thread pool.

        Args:
            wait: Whether to wait for pending tasks to complete
        """
        if self.executor:
            self.executor.shutdown(wait=wait)
            logger.info("ThreadPool shutdown")

    def _collect_results(self) -> List[WorkerResult]:
        """Collect all task results.

        Returns:
            List of WorkerResult objects
        """
        return list(self.results.values())