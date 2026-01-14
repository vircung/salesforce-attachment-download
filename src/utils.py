"""
Common Utilities

Basic utility functions used across the application with no external dependencies.
This module is intentionally kept minimal to avoid circular imports.
"""

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def setup_logging(log_file: Path) -> None:
    """
    Configure logging to file and console.

    Args:
        log_file: Path to the log file where logs will be written
    """
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )


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
