"""
Logging Module - Progress-Aware Logging System

Provides dynamic console handler management to resolve logging/progress display conflicts.
When progress tracking is active, console logging is intelligently managed to avoid
visual interference while preserving all file logging functionality.

Key Features:
- Dynamic console handler control during progress tracking
- Critical message display (errors) within progress UI
- Warning message buffering for post-progress display
- Thread-safe handler management
- Backward compatibility when progress is disabled

Usage:
    from src.logging import LoggingManager
    
    # Basic setup (replaces utils.setup_logging)
    manager = LoggingManager()
    manager.setup(log_file, console_level)
    
    # Progress mode (automatic via ProgressTracker integration)
    with manager.progress_mode():
        # Console logging suppressed, file logging preserved
        # Critical errors shown in progress UI
        pass
"""

from src.logging.manager import LoggingManager
from src.logging.handlers import ProgressAwareConsoleHandler
from src.logging.critical_display import CriticalMessageDisplay

__all__ = [
    'LoggingManager',
    'ProgressAwareConsoleHandler', 
    'CriticalMessageDisplay'
]