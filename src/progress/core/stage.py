"""
Core Progress Stage Module

Defines the base ProgressStage class and stage status enumeration.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from threading import RLock
from typing import Dict, Any, Optional, List, Callable

logger = logging.getLogger(__name__)


class StageStatus(Enum):
    """Enumeration of progress stage statuses."""
    PENDING = "pending"
    RUNNING = "running" 
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StageProgress:
    """Data structure for stage progress information."""
    current: int = 0
    total: Optional[int] = None
    status: StageStatus = StageStatus.PENDING
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class ProgressStage(ABC):
    """
    Abstract base class for progress stages.
    
    Each stage represents a major phase in the workflow (CSV processing, 
    SOQL querying, file downloads) and provides structured progress updates.
    """

    def __init__(self, name: str, description: str = "") -> None:
        """
        Initialize a progress stage.
        
        Args:
            name: Unique stage name (e.g., "csv_processing")
            description: Human-readable description
        """
        self.name = name
        self.description = description
        self._lock = RLock()
        self._progress = StageProgress()
        self._callbacks: List[Callable] = []

    @property
    def progress(self) -> StageProgress:
        """Get current progress state (thread-safe)."""
        with self._lock:
            return StageProgress(
                current=self._progress.current,
                total=self._progress.total,
                status=self._progress.status,
                message=self._progress.message,
                details=dict(self._progress.details),
                error=self._progress.error,
            )

    def add_callback(self, callback: Callable) -> None:
        """
        Add callback function to be called when progress updates.
        
        Args:
            callback: Function that accepts (stage_name, progress) arguments
        """
        with self._lock:
            if callback not in self._callbacks:
                self._callbacks.append(callback)

    def remove_callback(self, callback: Callable) -> None:
        """Remove previously added callback."""
        with self._lock:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

    def _notify_callbacks(self):
        """Notify all registered callbacks of progress change."""
        # Make copy of callbacks to avoid lock contention
        with self._lock:
            callbacks_copy = self._callbacks.copy()
            progress_copy = self.progress
        
        # Call callbacks without holding lock
        for callback in callbacks_copy:
            try:
                callback(self.name, progress_copy)
            except Exception as e:
                # Let errors propagate for debugging
                logger.warning(f"Callback error for {self.name}: {e}", exc_info=True)

    def update_progress(
        self, 
        current: Optional[int] = None,
        total: Optional[int] = None,
        message: str = "",
        details: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ) -> None:
        """
        Update stage progress information.
        
        Args:
            current: Current progress value
            total: Total expected value
            message: Status message
            details: Additional detail information
            error: Error message (if any)
        """
        with self._lock:
            if current is not None:
                self._progress.current = current
            if total is not None:
                self._progress.total = total
            if message:
                self._progress.message = message
            if details is not None:
                # Simple details update without memory management
                self._progress.details.update(details)
            if error is not None:
                self._progress.error = error
        
        self._notify_callbacks()

    def start(self, total: Optional[int] = None, message: str = "") -> None:
        """Mark stage as started."""
        with self._lock:
            self._progress.status = StageStatus.RUNNING
            self._progress.current = 0
            if total is not None:
                self._progress.total = total
            if message:
                self._progress.message = message
            self._progress.error = None
        
        self._notify_callbacks()

    def complete(self, message: str = ""):
        """Mark stage as completed."""
        with self._lock:
            if self._progress.status in (StageStatus.COMPLETED, StageStatus.FAILED, StageStatus.SKIPPED):
                return
            self._progress.status = StageStatus.COMPLETED
            if message:
                self._progress.message = message
            # Set current to total if total is known
            if self._progress.total is not None:
                self._progress.current = self._progress.total
        
        self._notify_callbacks()
 
    def fail(self, error: str, message: str = ""):
        """Mark stage as failed."""
        with self._lock:
            if self._progress.status in (StageStatus.COMPLETED, StageStatus.FAILED, StageStatus.SKIPPED):
                return
            self._progress.status = StageStatus.FAILED
            self._progress.error = error
            if message:
                self._progress.message = message
        
        self._notify_callbacks()
 
    def skip(self, message: str = ""):
        """Mark stage as skipped."""
        with self._lock:
            if self._progress.status in (StageStatus.COMPLETED, StageStatus.FAILED, StageStatus.SKIPPED):
                return
            self._progress.status = StageStatus.SKIPPED
            if message:
                self._progress.message = message
        
        self._notify_callbacks()


    def reset(self) -> None:
        """Reset stage to initial state."""
        with self._lock:
            self._progress = StageProgress()
        
        self._notify_callbacks()

    @abstractmethod
    def get_display_info(self) -> Dict[str, Any]:
        """
        Get stage-specific information for display.
        
        Returns:
            Dictionary containing display-friendly information about the stage
        """
        pass

    def __str__(self) -> str:
        """String representation of the stage."""
        progress = self.progress
        return f"{self.name} ({progress.status.value}): {progress.message}"
