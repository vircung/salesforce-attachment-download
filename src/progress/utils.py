"""
Progress Utilities

Helper functions for setting up and managing progress tracking.
"""

import logging

from .core import ProgressTracker, ProgressMode

DETAIL_KEYS_BY_STAGE = {
    "csv_processing": ["current_csv", "current_records", "total_records"],
    "soql_query": ["current_csv", "current_batch", "total_attachments"],
    "file_downloads": ["bucket", "current_file", "speed", "success_count", "failed_count", "skipped_count"],
}

DETAIL_LABELS = {
    "current_csv": "csv",
    "current_records": "records",
    "total_records": "total_records",
    "current_batch": "batch",
    "total_attachments": "total_attachments",
    "bucket": "bucket",
    "current_file": "file",
    "speed": "speed",
    "success_count": "ok",
    "failed_count": "fail",
    "skipped_count": "skip",
}


def get_detail_display_items(stage_name: str, details: dict) -> list:
    """Return ordered (label, value) pairs for display."""
    keys = DETAIL_KEYS_BY_STAGE.get(stage_name, list(details.keys()))
    items = []
    for key in keys:
        value = details.get(key)
        if value is None or value == "":
            continue
        label = DETAIL_LABELS.get(key, key)
        items.append((label, value))
    return items

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

