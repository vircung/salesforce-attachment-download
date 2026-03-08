"""Pre-download scan and skipped-files management.

Scans the output directory to identify already-downloaded files,
loads permanently-skipped attachment IDs, and writes skipped-files reports.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Set

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


def load_skipped_attachment_ids(skipped_files_path: Path) -> Set[str]:
    """Read skipped_files.json and return a set of attachment_ids to exclude.

    Args:
        skipped_files_path: Direct path to skipped_files.json

    Returns empty set if file doesn't exist or is malformed.
    """
    if not skipped_files_path.exists():
        return set()

    try:
        with open(skipped_files_path, 'r', encoding='utf-8') as f:
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
                len(skipped_ids), skipped_files_path
            )

        return skipped_ids

    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read skipped_files.json: %s", e)
        return set()


def write_skipped_files_report(
    os_errors: List[Dict[str, Any]],
    skipped_files_path: Path,
    instance_url: str,
) -> None:
    """Write a JSON report of files skipped due to OS errors.

    Merges with existing entries and deduplicates by attachment_id.
    Includes a manual download URL for each file.

    Args:
        os_errors: List of error dicts with 'id', 'parent_id', 'name', 'error' keys
        skipped_files_path: Direct path to skipped_files.json
        instance_url: Salesforce instance URL for manual download links
    """
    if not instance_url.startswith('https://'):
        instance_url = f"https://{instance_url}" if instance_url else ''

    # Load existing report if present (multiple objects may append)
    existing_entries = []
    if skipped_files_path.exists():
        try:
            with open(skipped_files_path, 'r', encoding='utf-8') as f:
                existing_entries = json.load(f)
        except (json.JSONDecodeError, OSError):
            existing_entries = []

    new_entries = []
    for err in os_errors:
        attachment_id = err.get('id', '')
        new_entries.append({
            'attachment_id': attachment_id,
            'parent_id': err.get('parent_id', ''),
            'original_name': err.get('name', ''),
            'error': err.get('error', ''),
            'manual_download_url': (
                f"{instance_url}/servlet/servlet.FileDownload?file={attachment_id}"
                if instance_url else ''
            ),
        })

    # Deduplicate by attachment_id
    merged = existing_entries + new_entries
    seen_ids: Set[str] = set()
    all_entries = []
    for entry in merged:
        aid = entry.get('attachment_id', '')
        if aid and aid in seen_ids:
            continue
        seen_ids.add(aid)
        all_entries.append(entry)

    try:
        skipped_files_path.parent.mkdir(parents=True, exist_ok=True)
        with open(skipped_files_path, 'w', encoding='utf-8') as f:
            json.dump(all_entries, f, indent=2, ensure_ascii=False)

        logger.warning(
            f"Wrote skipped files report ({len(new_entries)} new, {len(all_entries)} total): "
            f"{skipped_files_path}"
        )
    except Exception as e:
        logger.error(f"Failed to write skipped files report: {e}")
