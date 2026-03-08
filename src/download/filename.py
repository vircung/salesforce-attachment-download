"""
Filename Utilities

Functions and classes for handling attachment filenames,
including sanitization and collision detection.
"""

import logging
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Tuple, Union

from src.models import AttachmentRecord

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
    attachments: List[AttachmentRecord]
) -> Dict[str, FilenameInfo]:
    """
    Detect filename collisions and pre-compute sanitized filenames.
    Uses lowercase comparison for collision detection to be filesystem-agnostic.

    Args:
        attachments: List of AttachmentRecord instances

    Returns:
        Dict mapping attachment id to FilenameInfo with safe_name and collision flag
    """
    # First pass: count occurrences per (parent_id, safe_name_lowercase)
    occurrence_count: Dict[Tuple[str, str], int] = defaultdict(int)
    attachment_info: Dict[str, Tuple[str, str, Tuple[str, str]]] = {}

    for attachment in attachments:
        attachment_id = attachment.id
        parent_id = attachment.parent_id or DEFAULT_PARENT_ID
        original_name = attachment.name or 'unnamed'
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


def get_fs_name_max(path: Path) -> int:
    """Get the maximum filename length for the filesystem at the given path.

    On Linux (ext4) this is typically 255 bytes.
    On Windows (NTFS) this is 255 characters.
    Falls back to 255 if detection fails.
    """
    try:
        if sys.platform == 'win32':
            # NTFS counts UTF-16 characters, effectively 255 chars
            return 255
        else:
            # Linux/macOS: use os.pathconf for the actual FS limit
            dir_path = str(path if path.is_dir() else path.parent)
            return os.pathconf(dir_path, 'PC_NAME_MAX')
    except (OSError, ValueError):
        return 255


def check_filename_length(filepath: Path, attachment_id: str = '') -> bool:
    """Check if a filename (including temp suffix) fits within the FS limit.

    On Linux, ext4 counts bytes (UTF-8), so multi-byte characters reduce
    the effective character limit. The temp file adds '.{attachment_id}.part'
    to the name, which must also fit.

    Returns True if the name fits, False if it would exceed the limit.
    Logs a warning when the name is too long.
    """
    name = filepath.name
    # The downloader creates a temp file with this suffix
    temp_suffix = f".{attachment_id}.part" if attachment_id else ".part"
    temp_name = f"{name}{temp_suffix}"

    name_max = get_fs_name_max(filepath)

    if sys.platform == 'win32':
        # NTFS: count characters
        name_len = len(temp_name)
    else:
        # ext4/APFS: count bytes
        name_len = len(temp_name.encode('utf-8'))

    if name_len > name_max:
        logger.warning(
            f"Filename too long ({name_len} > {name_max}): "
            f"attachment {attachment_id}, name '{name[:80]}...'"
        )
        return False

    return True


def build_output_filename(
    attachment: AttachmentRecord,
    filename_info_map: Dict[str, 'FilenameInfo']
) -> str:
    """Build the output filename for an attachment.

    Uses {parent_id}_{safe_name} normally,
    or {parent_id}_{attachment_id}_{safe_name} when a collision is detected.
    """
    attachment_id = attachment.id
    parent_id = attachment.parent_id or DEFAULT_PARENT_ID

    filename_info = filename_info_map.get(attachment_id)
    if filename_info:
        safe_name = filename_info.safe_name
        has_collision = filename_info.has_collision
    else:
        safe_name = sanitize_filename(attachment.name or 'unnamed')
        has_collision = False

    if has_collision:
        return f"{parent_id}_{attachment_id}_{safe_name}"
    else:
        return f"{parent_id}_{safe_name}"
