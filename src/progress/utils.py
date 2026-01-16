"""
Progress Utilities

Helper functions for setting up and managing progress tracking.
"""

import logging

from .core import ProgressTracker, ProgressMode

logger = logging.getLogger(__name__)


def create_progress_tracker(mode_str: str = "auto") -> ProgressTracker:
    """
    Create a progress tracker with the specified mode.
    
    Args:
        mode_str: Progress mode string ("auto", "on", "off")
        
    Returns:
        ProgressTracker instance
    """
    try:
        mode = ProgressMode(mode_str.lower())
    except ValueError:
        logger.warning(f"Invalid progress mode '{mode_str}', using 'auto'")
        mode = ProgressMode.AUTO
    
    return ProgressTracker(mode=mode)

