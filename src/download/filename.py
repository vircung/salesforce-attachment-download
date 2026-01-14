"""
Filename Utilities

Functions and classes for handling attachment filenames,
including sanitization and collision detection.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import List, Dict, Tuple

logger = logging.getLogger(__name__)

# Maximum filename length supported by most filesystems
MAX_FILENAME_LENGTH = 255

# Default value for attachments without ParentId
DEFAULT_PARENT_ID = 'NO_PARENT'


@dataclass
class FilenameInfo:
    """Pre-computed filename information for an attachment."""
    safe_name: str
    has_collision: bool


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to be filesystem-safe.

    Removes or replaces characters that may cause issues on
    Windows, Linux, or macOS filesystems. Also truncates filenames
    that exceed the maximum length.

    Args:
        filename: Original filename to sanitize

    Returns:
        Sanitized filename safe for filesystem use
    """
    # Replace problematic characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')

    # Limit length to maximum supported by most filesystems
    if len(filename) > MAX_FILENAME_LENGTH:
        name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
        max_name_length = MAX_FILENAME_LENGTH - len(ext) - 1
        filename = name[:max_name_length] + '.' + ext if ext else name[:MAX_FILENAME_LENGTH]

    return filename


def detect_filename_collisions(
    attachments: List[Dict[str, str]]
) -> Dict[str, FilenameInfo]:
    """
    Detect filename collisions and pre-compute sanitized filenames.
    Uses lowercase comparison for collision detection to be filesystem-agnostic.

    Args:
        attachments: List of attachment dictionaries with Id, ParentId, Name

    Returns:
        Dict mapping attachment Id to FilenameInfo with safe_name and collision flag
    """
    # First pass: count occurrences per (parent_id, safe_name_lowercase)
    occurrence_count: Dict[Tuple[str, str], int] = defaultdict(int)
    attachment_info: Dict[str, Tuple[str, str, Tuple[str, str]]] = {}

    for attachment in attachments:
        attachment_id = attachment['Id']
        parent_id = attachment.get('ParentId', DEFAULT_PARENT_ID)
        original_name = attachment.get('Name', 'unnamed')
        safe_name = sanitize_filename(original_name)

        # Use lowercase for collision detection (filesystem-agnostic)
        collision_key = (parent_id, safe_name.lower())
        occurrence_count[collision_key] += 1
        attachment_info[attachment_id] = (parent_id, safe_name, collision_key)

    # Second pass: build result with collision flags
    result: Dict[str, FilenameInfo] = {}
    for attachment_id, (parent_id, safe_name, collision_key) in attachment_info.items():
        has_collision = occurrence_count[collision_key] > 1
        result[attachment_id] = FilenameInfo(
            safe_name=safe_name,
            has_collision=has_collision
        )

    # Log collision statistics
    total_collisions = sum(1 for info in result.values() if info.has_collision)
    if total_collisions > 0:
        logger.warning(
            f"Detected {total_collisions} file(s) with name collisions - "
            f"will use Id prefix for these files"
        )
    else:
        logger.info("No filename collisions detected")

    return result
