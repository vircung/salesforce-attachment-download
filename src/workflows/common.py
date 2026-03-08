"""
Common Workflow Utilities

Shared helper functions for workflow modules.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def ensure_directories(*dirs: Path) -> None:
    """Create multiple directories if they don't exist."""
    for directory in dirs:
        directory.mkdir(parents=True, exist_ok=True)
