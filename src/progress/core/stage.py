"""
Core Progress Stage Module

Defines the base ProgressStage class and stage status enumeration.
"""

import logging
import time
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
        
        # Progress caching for performance
        self._cached_progress: Optional[StageProgress] = None
        self._cache_dirty = True
        self._cache_update_count = 0
        
        # Error tracking for callbacks
        self._callback_errors: Dict[Callable, int] = {}
        self._disabled_callbacks: set = set()
        
        # Memory management for details
        self._details_history: List[Dict[str, Any]] = []
        self._last_cleanup_time = time.time()

    @property
    def progress(self) -> StageProgress:
        """Get current progress state (thread-safe with caching)."""
        from src.progress.config import get_config
        config = get_config()
        
        with self._lock:
            # Use cached copy if available and not dirty
            if (config.enable_progress_caching and 
                not self._cache_dirty and 
                self._cached_progress is not None):
                return self._cached_progress
            
            # Create fresh copy
            progress_copy = StageProgress(
                current=self._progress.current,
                total=self._progress.total,
                status=self._progress.status,
                message=self._progress.message,
                details=self._progress.details.copy(),
                error=self._progress.error
            )
            
            # Cache the copy if caching is enabled
            if config.enable_progress_caching:
                self._cached_progress = progress_copy
                self._cache_dirty = False
                self._cache_update_count = 0
            
            return progress_copy

    def add_callback(self, callback: Callable) -> None:
        """
        Add callback function to be called when progress updates.
        
        Args:
            callback: Function that accepts (stage_name, progress) arguments
        """
        with self._lock:
            if callback not in self._callbacks and callback not in self._disabled_callbacks:
                self._callbacks.append(callback)
                self._callback_errors[callback] = 0

    def remove_callback(self, callback: Callable) -> None:
        """Remove previously added callback."""
        with self._lock:
            if callback in self._callbacks:
                self._callbacks.remove(callback)
            if callback in self._callback_errors:
                del self._callback_errors[callback]
            self._disabled_callbacks.discard(callback)

    def _notify_callbacks(self):
        """Notify all registered callbacks of progress change with error handling."""
        from src.progress.config import get_config
        config = get_config()
        
        # Make copy of callbacks to avoid lock contention
        with self._lock:
            # Filter out disabled callbacks
            active_callbacks = [
                cb for cb in self._callbacks 
                if cb not in self._disabled_callbacks
            ]
            callbacks_copy = active_callbacks.copy()
            progress_copy = self.progress
        
        # Call callbacks without holding lock
        for callback in callbacks_copy:
            try:
                callback(self.name, progress_copy)
                # Reset error count on successful call
                with self._lock:
                    self._callback_errors[callback] = 0
                    
            except Exception as e:
                with self._lock:
                    # Increment error count
                    self._callback_errors[callback] = self._callback_errors.get(callback, 0) + 1
                    
                    # Log error if configured
                    if config.log_callback_errors:
                        logger.warning(
                            f"Callback error in stage {self.name}: {e}. "
                            f"Error count: {self._callback_errors[callback]}"
                        )
                    
                    # Disable callback if too many errors
                    if self._callback_errors[callback] >= config.max_callback_errors:
                        logger.error(
                            f"Disabling callback in stage {self.name} due to too many errors "
                            f"({self._callback_errors[callback]})"
                        )
                        self._disabled_callbacks.add(callback)
                        if callback in self._callbacks:
                            self._callbacks.remove(callback)

    def update_progress(
        self, 
        current: Optional[int] = None,
        total: Optional[int] = None,
        message: str = "",
        details: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ) -> None:
        """
        Update stage progress information with memory management.
        
        Args:
            current: Current progress value
            total: Total expected value
            message: Status message
            details: Additional detail information
            error: Error message (if any)
        """
        from src.progress.config import get_config
        config = get_config()
        
        with self._lock:
            # Mark cache as dirty
            self._cache_dirty = True
            self._cache_update_count += 1
            
            # Force cache refresh if too many updates
            if self._cache_update_count >= config.cache_dirty_threshold:
                self._cached_progress = None
            
            if current is not None:
                self._progress.current = current
            if total is not None:
                self._progress.total = total
            if message:
                self._progress.message = message
            if details is not None:
                self._manage_details_memory(details)
            if error is not None:
                self._progress.error = error
        
        self._notify_callbacks()

    def _manage_details_memory(self, new_details: Dict[str, Any]):
        """Manage memory usage for details dictionary."""
        from src.progress.config import get_config
        config = get_config()
        
        # Update current details
        self._progress.details.update(new_details)
        
        # Add to history for potential cleanup
        self._details_history.append(new_details.copy())
        
        # Cleanup if we have too many entries
        if len(self._progress.details) > config.max_details_entries:
            # Keep only the most recent entries
            keys_to_remove = list(self._progress.details.keys())[:-config.max_details_entries//2]
            for key in keys_to_remove:
                self._progress.details.pop(key, None)
        
        # Cleanup history
        if len(self._details_history) > config.max_history_size:
            self._details_history = self._details_history[-config.max_history_size//2:]
        
        # Periodic cleanup
        current_time = time.time()
        if current_time - self._last_cleanup_time > 60.0:  # Cleanup every minute
            self._cleanup_old_details()
            self._last_cleanup_time = current_time

    def _cleanup_old_details(self) -> None:
        """Clean up old details entries that are no longer relevant."""
        # Remove entries that haven't been updated recently
        # This is a simple heuristic - in practice, you might want more sophisticated logic
        if len(self._progress.details) > 20:  # Only cleanup if we have many entries
            # Keep only half the entries (most recent ones based on insertion order)
            items = list(self._progress.details.items())
            items_to_keep = items[-len(items)//2:]
            self._progress.details = dict(items_to_keep)

    def start(self, total: Optional[int] = None, message: str = "") -> None:
        """Mark stage as started."""
        with self._lock:
            self._cache_dirty = True
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
            self._cache_dirty = True
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
            self._cache_dirty = True
            self._progress.status = StageStatus.FAILED
            self._progress.error = error
            if message:
                self._progress.message = message
        
        self._notify_callbacks()

    def skip(self, message: str = ""):
        """Mark stage as skipped."""
        with self._lock:
            self._cache_dirty = True
            self._progress.status = StageStatus.SKIPPED
            if message:
                self._progress.message = message
        
        self._notify_callbacks()

    def reset(self) -> None:
        """Reset stage to initial state."""
        with self._lock:
            self._cache_dirty = True
            self._cached_progress = None
            self._progress = StageProgress()
            # Reset error tracking
            self._callback_errors.clear()
            self._disabled_callbacks.clear()
            self._details_history.clear()
        
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