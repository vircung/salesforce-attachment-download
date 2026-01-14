"""
Common Utilities

Basic utility functions used across the application with no external dependencies.
This module is intentionally kept minimal to avoid circular imports.
"""

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def setup_logging(log_file: Path, console_level: int = logging.WARNING) -> None:
    """
    Configure logging to file and console with different log levels.
    
    File handler always logs at DEBUG level (full details for analysis).
    Console handler uses the specified level (WARNING/INFO/DEBUG based on flags).

    Args:
        log_file: Path to the log file where logs will be written
        console_level: Logging level for console output (default: WARNING)
                      - WARNING: Only errors and warnings (minimal output)
                      - INFO: Progress updates and main workflow steps (--verbose)
                      - DEBUG: All technical details (--debug)
    """
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # Create formatters
    # Detailed format for file (includes module name)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Simpler format for console (more readable)
    console_formatter = logging.Formatter(
        '%(levelname)s - %(message)s' if console_level >= logging.INFO 
        else '%(message)s'
    )

    # Create file handler (always DEBUG level for full logs)
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)

    # Create console handler (configurable level)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(console_formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture all levels
    
    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()
    
    # Add both handlers
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)


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
