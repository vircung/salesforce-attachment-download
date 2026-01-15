"""
Progress-Aware Console Handler

Custom logging handler that integrates with progress tracking to avoid
console output conflicts during progress display.
"""

import logging
import sys
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.logging.manager import LoggingManager


class ProgressAwareConsoleHandler(logging.StreamHandler):
    """
    Console handler that respects progress mode.
    
    When progress mode is active:
    - ERROR messages are displayed immediately via Rich panels
    - WARNING messages are buffered for later display
    - INFO/DEBUG messages are suppressed
    
    When progress mode is inactive:
    - Normal console logging behavior (all levels displayed)
    """
    
    def __init__(self, stream=None, logging_manager: Optional['LoggingManager'] = None) -> None:
        """
        Initialize progress-aware console handler.
        
        Args:
            stream: Output stream (default: sys.stdout)
            logging_manager: LoggingManager instance for coordination
        """
        super().__init__(stream or sys.stdout)
        self._logging_manager = logging_manager
        self._progress_mode = False
    
    def set_progress_mode(self, enabled: bool) -> None:
        """Enable or disable progress mode."""
        self._progress_mode = enabled
    
    def emit(self, record: logging.LogRecord) -> None:
        """
        Emit a log record with progress-aware handling.
        
        Args:
            record: LogRecord to emit
        """
        try:
            # If progress mode is not active, use normal handler behavior
            if not self._progress_mode:
                super().emit(record)
                return
            
            # Progress mode is active - handle based on log level
            if record.levelno >= logging.ERROR:
                # ERROR and CRITICAL: Display immediately in progress UI
                if self._logging_manager:
                    self._logging_manager.display_critical_error(record)
                else:
                    # Fallback to stderr if no manager
                    self._emit_to_stderr(record)
            
            elif record.levelno >= logging.WARNING:
                # WARNING: Buffer for later display
                if self._logging_manager:
                    self._logging_manager.buffer_warning(record)
                # Note: No fallback output to avoid progress interference
            
            # INFO and DEBUG: Suppressed during progress (but still go to file)
            # This prevents log interference with progress display
            
        except Exception:
            # Ensure emit() doesn't raise exceptions
            self.handleError(record)
    
    def _emit_to_stderr(self, record: logging.LogRecord) -> None:
        """
        Fallback method to emit to stderr.
        
        Used when LoggingManager is not available but we need
        to display critical errors during progress mode.
        """
        try:
            message = self.format(record)
            sys.stderr.write(f"{message}\n")
            sys.stderr.flush()
        except Exception:
            pass  # Avoid cascading errors
    
    def handleError(self, record: logging.LogRecord) -> None:
        """
        Handle errors that occur during emit().
        
        Override to provide better error handling during progress mode.
        """
        try:
            # If in progress mode, try to output error info to stderr
            if self._progress_mode:
                sys.stderr.write(f"Logging error occurred\n")
                sys.stderr.flush()
            else:
                # Use default handler behavior
                super().handleError(record)
        except Exception:
            pass  # Final fallback - don't let error handling fail