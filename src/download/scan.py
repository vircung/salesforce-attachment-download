"""Pre-download scan and skipped-files management.

Scans the output directory to identify already-downloaded files
and loads permanently-skipped attachment IDs from execution reports.
"""

import json
import logging
from pathlib import Path
from typing import Set

logger = logging.getLogger(__name__)


def scan_existing_files(output_dir: Path) -> Set[str]:
    """Scan output directory and return a set of existing filenames.

    Ignores subdirectories and .part files.
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

    # Backward compat: also scan files/ subdir from old layout
    files_subdir = output_dir / 'files'
    if files_subdir.is_dir():
        logger.info("Scan: found legacy files/ subdir in %s", output_dir)
        pre_legacy_count = len(existing)
        for entry in files_subdir.iterdir():
            if entry.is_dir() or entry.name.endswith('.part'):
                continue
            existing.add(entry.name)
        legacy_count = len(existing) - pre_legacy_count
        if legacy_count > 0:
            logger.info("Scan: %d additional files from legacy files/ subdir",
                         legacy_count)

    return existing


def load_skipped_attachment_ids(report_path: Path) -> Set[str]:
    """Load attachment IDs to permanently skip from report_missing.json.

    Supports two formats:
    - Wrapper format (report_missing.json): {"entries": [{"attachment_id": ...}, ...]}
    - Legacy flat list (skipped_files.json): [{"attachment_id": ...}, ...]

    Falls back to skipped_files.json in the same directory if report_missing.json
    doesn't exist.

    Returns empty set if no file exists or is malformed.
    """
    # Try report_missing.json first, fall back to legacy skipped_files.json
    paths_to_try = [report_path]
    legacy_path = report_path.parent / 'skipped_files.json'
    if legacy_path != report_path:
        paths_to_try.append(legacy_path)

    for path in paths_to_try:
        if not path.exists():
            continue

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Wrapper format: {"entries": [...]}
            if isinstance(data, dict) and 'entries' in data:
                entries = data['entries']
            # Legacy flat list format: [...]
            elif isinstance(data, list):
                entries = data
            else:
                logger.warning("Unexpected format in %s, ignoring", path)
                continue

            skipped_ids = {
                entry.get('attachment_id', '')
                for entry in entries
                if isinstance(entry, dict) and entry.get('attachment_id')
            }

            if skipped_ids:
                logger.info(
                    "Loaded %d permanently-skipped attachment IDs from %s",
                    len(skipped_ids), path
                )

            return skipped_ids

        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read %s: %s", path, e)
            continue

    return set()
