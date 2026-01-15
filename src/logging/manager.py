"""
Logging Manager - Core Handler Management

Main LoggingManager class that provides dynamic console handler control,
message buffering, and progress mode coordination.
"""

import logging
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import List, Optional, Dict, Any, Tuple, Iterator

from src.logging.handlers import ProgressAwareConsoleHandler
from src.logging.critical_display import CriticalMessageDisplay

logger = logging.getLogger(__name__)


class LoggingManager:
    """
    Thread-safe logging manager with dynamic console handler control.
    
    Manages console and file logging handlers dynamically based on progress mode.
    When progress is active, console output is suppressed to avoid interference
    with Rich progress displays, while preserving all file logging.
    
    Features:
    - Dynamic handler enable/disable
    - Message buffering for warnings during progress
    - Critical error display integration with progress UI
    - Thread-safe operations with proper locking
    - Context manager support with guaranteed cleanup
    """
    
    # Class-level lock for thread safety across instances
    _global_lock = RLock()
    _instance: Optional['LoggingManager'] = None
    
    def __init__(self) -> None:
        """Initialize logging manager with thread-safe state."""
        self._lock = RLock()
        self._console_handler: Optional[ProgressAwareConsoleHandler] = None
        self._file_handler: Optional[logging.FileHandler] = None
        self._original_handlers: List[logging.Handler] = []
        
        # Progress mode state
        self._progress_mode_active = False
        self._progress_mode_count = 0  # Track nested calls
        
        # Message buffering
        self._buffered_warnings: List[Tuple[float, str, Dict[str, Any]]] = []
        self._max_buffered_messages = 50  # Prevent memory issues
        
        # Critical message display integration
        self._critical_display: Optional[CriticalMessageDisplay] = None
        
        # Thread safety for callbacks
        self._callback_lock = RLock()
        
        # Progress tracker reference for integrated error display
        self._progress_tracker: Optional[object] = None
        
    @classmethod
    def get_instance(cls) -> 'LoggingManager':
        """Get or create singleton instance (thread-safe)."""
        if cls._instance is None:
            with cls._global_lock:
                if cls._instance is None:
                    cls._instance = LoggingManager()
        return cls._instance
    
    def setup(self, log_file: Path, console_level: int = logging.WARNING) -> None:
        """
        Configure logging to file and console with different log levels.
        
        Replaces the functionality of utils.setup_logging() with progress-aware
        console handler management.
        
        Args:
            log_file: Path to the log file where logs will be written
            console_level: Logging level for console output (default: WARNING)
                          - WARNING: Only errors and warnings (minimal output)
                          - INFO: Progress updates and main workflow steps (--verbose)
                          - DEBUG: All technical details (--debug)
        """
        with self._lock:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Create formatters
            file_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            
            console_formatter = logging.Formatter(
                '%(levelname)s - %(message)s' if console_level >= logging.INFO 
                else '%(message)s'
            )
            
            # Create file handler (always DEBUG level for full logs)
            self._file_handler = logging.FileHandler(log_file)
            self._file_handler.setLevel(logging.DEBUG)
            self._file_handler.setFormatter(file_formatter)
            
            # Create progress-aware console handler
            self._console_handler = ProgressAwareConsoleHandler(
                stream=sys.stdout,
                logging_manager=self
            )
            self._console_handler.setLevel(console_level)
            self._console_handler.setFormatter(console_formatter)
            
            # Configure root logger
            root_logger = logging.getLogger()
            root_logger.setLevel(logging.DEBUG)
            
            # Store original handlers before replacement
            self._original_handlers = root_logger.handlers.copy()
            
            # Replace handlers
            root_logger.handlers.clear()
            root_logger.addHandler(self._file_handler)
            root_logger.addHandler(self._console_handler)
            
            logger.debug("Logging manager setup complete")
    
    def enable_progress_mode(self) -> None:
        """
        Enable progress mode - suppress console logging.
        
        Thread-safe with reference counting for nested calls.
        Console logging is disabled but file logging continues.
        """
        with self._lock:
            self._progress_mode_count += 1
            
            if not self._progress_mode_active:
                self._progress_mode_active = True
                
                if self._console_handler:
                    self._console_handler.set_progress_mode(True)
                    logger.debug("Console handler progress mode enabled")
                else:
                    logger.warning("No console handler found when enabling progress mode")
                
                # Clear any existing buffered warnings
                self._buffered_warnings.clear()
                
                logger.debug("Progress mode enabled - console logging suppressed")
    
    def disable_progress_mode(self) -> None:
        """
        Disable progress mode - restore console logging.
        
        Thread-safe with reference counting. Only disables when all nested
        calls have completed. Displays any buffered warning messages.
        """
        with self._lock:
            if self._progress_mode_count > 0:
                self._progress_mode_count -= 1
            
            if self._progress_mode_count == 0 and self._progress_mode_active:
                self._progress_mode_active = False
                
                if self._console_handler:
                    self._console_handler.set_progress_mode(False)
                    logger.debug("Console handler progress mode disabled")
                
                # Display buffered warnings
                self._display_buffered_warnings()
                
                logger.debug("Progress mode disabled - console logging restored")
    
    @contextmanager
    def progress_mode(self) -> Iterator[None]:
        """
        Context manager for progress mode with guaranteed cleanup.
        
        Usage:
            with logging_manager.progress_mode():
                # Console logging suppressed
                # Progress UI can display cleanly
                pass
            # Console logging automatically restored
        """
        self.enable_progress_mode()
        try:
            yield
        finally:
            self.disable_progress_mode()
    
    def is_progress_mode_active(self) -> bool:
        """Check if progress mode is currently active."""
        with self._lock:
            return self._progress_mode_active
    
    def buffer_warning(self, record: logging.LogRecord) -> None:
        """
        Buffer a warning message for later display.
        
        Called by ProgressAwareConsoleHandler when progress mode is active
        and a WARNING level message needs to be buffered.
        
        Args:
            record: LogRecord to buffer
        """
        with self._callback_lock:
            # Prevent memory issues with too many buffered messages
            if len(self._buffered_warnings) >= self._max_buffered_messages:
                # Remove oldest message
                self._buffered_warnings.pop(0)
            
            # Store timestamp, formatted message, and record details
            formatted_message = self._console_handler.format(record) if self._console_handler else str(record.msg)
            
            self._buffered_warnings.append((
                time.time(),
                formatted_message,
                {
                    'level': record.levelno,
                    'name': record.name,
                    'funcName': record.funcName,
                    'lineno': record.lineno
                }
            ))
    
    def display_critical_error(self, record: logging.LogRecord) -> None:
        """
        Display critical error immediately during progress mode.
        
        Called by ProgressAwareConsoleHandler when progress mode is active
        and an ERROR level message needs immediate display.
        
        Args:
            record: LogRecord to display
        """
        try:
            # Use standalone critical display 
            if not self._critical_display:
                self._critical_display = CriticalMessageDisplay()
            
            self._critical_display.display_error(record)
            
        except Exception as e:
            # Final fallback to stderr if Rich display fails
            try:
                message = record.getMessage() if hasattr(record, 'getMessage') else str(record.msg)
                sys.stderr.write(f"ERROR: {message}\n")
                sys.stderr.flush()
            except Exception:
                sys.stderr.write(f"ERROR: {record.msg}\n")
                sys.stderr.flush()
    
    def _display_buffered_warnings(self) -> None:
        """Display all buffered warning messages when progress mode ends."""
        if not self._buffered_warnings:
            return
        
        try:
            # Display summary header
            print(f"\n⚠️  {len(self._buffered_warnings)} warning(s) occurred during processing:")
            print("-" * 60)
            
            # Display each buffered warning
            for timestamp, message, details in self._buffered_warnings:
                elapsed = time.time() - timestamp
                print(f"[{elapsed:.1f}s ago] {message}")
            
            print("-" * 60)
            
        except Exception as e:
            logger.error(f"Failed to display buffered warnings: {e}")
        finally:
            # Clear buffer
            self._buffered_warnings.clear()
    
    def set_critical_display(self, display: Optional[CriticalMessageDisplay]) -> None:
        """Set the critical message display handler."""
        with self._lock:
            self._critical_display = display
    
    def set_progress_tracker(self, progress_tracker: Optional[object]) -> None:
        """Set progress tracker reference for integrated error display."""
        with self._lock:
            self._progress_tracker = progress_tracker
    
    def cleanup(self) -> None:
        """
        Clean up logging manager resources.
        
        Restores original handlers and ensures proper cleanup.
        Thread-safe with proper exception handling.
        """
        with self._lock:
            try:
                # Force disable progress mode
                self._progress_mode_active = False
                self._progress_mode_count = 0
                
                # Display any remaining buffered warnings
                self._display_buffered_warnings()
                
                # Restore original handlers if available
                if self._original_handlers:
                    root_logger = logging.getLogger()
                    root_logger.handlers.clear()
                    root_logger.handlers.extend(self._original_handlers)
                
                # Close file handler
                if self._file_handler:
                    try:
                        self._file_handler.close()
                    except Exception:
                        pass
                
                logger.debug("Logging manager cleanup complete")
                
            except Exception as e:
                # Ensure cleanup doesn't fail completely
                sys.stderr.write(f"Warning: Logging manager cleanup error: {e}\n")
    
    def __del__(self) -> None:
        """Destructor - ensure cleanup on garbage collection."""
        try:
            self.cleanup()
        except Exception:
            pass  # Avoid exceptions during garbage collection


# Convenience function to maintain backward compatibility
def setup_logging(log_file: Path, console_level: int = logging.WARNING) -> LoggingManager:
    """
    Setup logging with progress-aware management.
    
    Replaces utils.setup_logging() while maintaining backward compatibility.
    
    Args:
        log_file: Path to the log file
        console_level: Console logging level
        
    Returns:
        LoggingManager instance for advanced control
    """
    manager = LoggingManager.get_instance()
    manager.setup(log_file, console_level)
    return manager