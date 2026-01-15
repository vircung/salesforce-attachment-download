"""
Common Utilities

Basic utility functions used across the application with no external dependencies.
This module is intentionally kept minimal to avoid circular imports.

Note: setup_logging has been moved to src.logging.manager for progress-aware functionality.
"""

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def setup_logging(log_file: Path, console_level: int = logging.WARNING) -> None:
    """
    Configure logging to file and console with different log levels.
    
    DEPRECATED: This function is maintained for backward compatibility.
    Use src.logging.LoggingManager for new code with progress-aware functionality.
    
    File handler always logs at DEBUG level (full details for analysis).
    Console handler uses the specified level (WARNING/INFO/DEBUG based on flags).

    Args:
        log_file: Path to the log file where logs will be written
        console_level: Logging level for console output (default: WARNING)
                      - WARNING: Only errors and warnings (minimal output)
                      - INFO: Progress updates and main workflow steps (--verbose)
                      - DEBUG: All technical details (--debug)
    """
    # Import here to avoid circular imports
    from .logging import LoggingManager
    
    # Use the new logging manager for backward compatibility
    manager = LoggingManager.get_instance()
    manager.setup(log_file, console_level)
    
    # Log deprecation warning
    logger.info("Using backward compatibility setup_logging - consider migrating to LoggingManager")


def log_section_header(title: str, width: int = 70) -> None:
    """
    Log a section header with visual separator.
    
    Creates a visually distinct section header in logs with the format:
    ======================================================================
    SECTION TITLE
    ======================================================================
    
    Args:
        title: Section title to display
        width: Width of separator line in characters (default: 70)
    
    Example:
        >>> log_section_header("STEP 1: Authentication")
        # Logs:
        # ======================================================================
        # STEP 1: Authentication
        # ======================================================================
    """
    separator = "=" * width
    logger.info(separator)
    logger.info(title)
    logger.info(separator)
