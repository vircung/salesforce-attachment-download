"""Pre-download scan for resume support.

Scans the output directory to identify already-downloaded files
and loads permanently-skipped attachment IDs from skipped_files.json.
"""

import json
import logging
from pathlib import Path
from typing import Set

logger = logging.getLogger(__name__)

# Directory used for partial downloads — excluded from scan
TMP_DIR_NAME = ".tmp_downloads"


def scan_existing_files(output_dir: Path) -> Set[str]:
    """Scan output directory and return a set of existing filenames.

    Ignores .tmp_downloads/ subdirectory and .part files.
    Returns empty set if directory doesn't exist.
    """
    if not output_dir.exists():
        logger.debug("Output directory does not exist: %s", output_dir)
        return set()

    existing = set()
    for entry in output_dir.iterdir():
        if entry.is_dir():
            continue
        if entry.name.endswith('.part'):
            continue
        existing.add(entry.name)

    logger.info("Scan: found %d existing files in %s", len(existing), output_dir)
    return existing


def load_skipped_attachment_ids(output_dir: Path) -> Set[str]:
    """Read skipped_files.json and return a set of attachment_ids to exclude.

    Navigates up from output_dir to find output/skipped_files.json.
    Returns empty set if file doesn't exist or is malformed.
    """
    # Navigate up to output/ directory
    report_dir = output_dir
    for _ in range(3):
        if report_dir.name == 'output':
            break
        report_dir = report_dir.parent

    report_path = report_dir / "skipped_files.json"

    if not report_path.exists():
        return set()

    try:
        with open(report_path, 'r', encoding='utf-8') as f:
            entries = json.load(f)

        if not isinstance(entries, list):
            logger.warning("skipped_files.json is not a list, ignoring")
            return set()

        skipped_ids = {
            entry.get('attachment_id', '')
            for entry in entries
            if isinstance(entry, dict) and entry.get('attachment_id')
        }

        if skipped_ids:
            logger.info(
                "Loaded %d permanently-skipped attachment IDs from %s",
                len(skipped_ids), report_path
            )

        return skipped_ids

    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read skipped_files.json: %s", e)
        return set()
