"""
Execution Report Writer

Writes report_downloaded.json and report_missing.json after each download run.
Supports resume merge: deduplicates downloaded entries, removes succeeded from missing.
"""

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

REPORT_DOWNLOADED = "report_downloaded.json"
REPORT_MISSING = "report_missing.json"


@dataclass
class ReportEntry:
    """Single attachment entry in a report."""
    attachment_id: str
    parent_id: str
    filename: str
    object_name: str
    download_url: str
    body_length: int = 0
    error: Optional[str] = None
    error_type: Optional[str] = None


def read_report(path: Path) -> Dict[str, Any]:
    """Read a report file. Returns empty structure if missing or invalid."""
    if not path.exists():
        return {"entries": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "entries" in data:
            return data
        return {"entries": []}
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Could not read report %s: %s", path, e)
        return {"entries": []}


def _build_report(
    entries: List[Dict[str, Any]],
    instance_url: str,
    output_dir: Path,
    stages_info: Dict[str, Any],
    total_queried: int,
    downloaded_count: int,
    missing_count: int,
    objects: List[str],
) -> Dict[str, Any]:
    """Build a report dict with metadata wrapper."""
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "instance_url": instance_url,
        "output_dir": str(output_dir.resolve()),
        "summary": {
            "total_queried": total_queried,
            "downloaded": downloaded_count,
            "missing": missing_count,
            "objects": objects,
        },
        "stages": stages_info,
        "entries": entries,
    }


def write_reports(
    output_dir: Path,
    downloaded: List[ReportEntry],
    missing: List[ReportEntry],
    instance_url: str,
    stages_info: Dict[str, Any],
    total_queried: int,
) -> None:
    """Write both report files, merging with existing reports on resume.

    - Downloaded: merge + deduplicate by attachment_id
    - Missing: merge new failures, remove entries that succeeded this run
    """
    downloaded_path = output_dir / REPORT_DOWNLOADED
    missing_path = output_dir / REPORT_MISSING

    # Convert new entries to dicts
    new_downloaded = [asdict(e) for e in downloaded]
    new_missing = [asdict(e) for e in missing]

    # IDs that succeeded this run — remove from missing
    succeeded_ids = {e.attachment_id for e in downloaded}

    # Merge with existing downloaded report
    existing_downloaded = read_report(downloaded_path)
    existing_dl_entries = existing_downloaded.get("entries", [])
    merged_downloaded = merge_entries(existing_dl_entries, new_downloaded)

    # Merge with existing missing report, removing succeeded entries
    existing_missing = read_report(missing_path)
    existing_ms_entries = existing_missing.get("entries", [])
    # Remove entries that succeeded this run
    filtered_existing_missing = [
        e for e in existing_ms_entries
        if e.get("attachment_id") not in succeeded_ids
    ]
    merged_missing = merge_entries(filtered_existing_missing, new_missing)

    # Collect all object names
    all_objects = sorted(set(
        e.get("object_name", "") for e in merged_downloaded + merged_missing
        if e.get("object_name")
    ))

    # Build and write reports
    dl_report = _build_report(
        entries=merged_downloaded,
        instance_url=instance_url,
        output_dir=output_dir,
        stages_info=stages_info,
        total_queried=total_queried,
        downloaded_count=len(merged_downloaded),
        missing_count=len(merged_missing),
        objects=all_objects,
    )
    ms_report = _build_report(
        entries=merged_missing,
        instance_url=instance_url,
        output_dir=output_dir,
        stages_info=stages_info,
        total_queried=total_queried,
        downloaded_count=len(merged_downloaded),
        missing_count=len(merged_missing),
        objects=all_objects,
    )

    write_json(downloaded_path, dl_report)
    write_json(missing_path, ms_report)

    logger.info(
        "Reports written: %d downloaded, %d missing → %s",
        len(merged_downloaded), len(merged_missing), output_dir,
    )


def merge_entries(
    existing: List[Dict[str, Any]],
    new: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Merge entry lists, deduplicating by attachment_id. New entries win."""
    by_id: Dict[str, Dict[str, Any]] = {}
    for entry in existing:
        aid = entry.get("attachment_id")
        if aid:
            by_id[aid] = entry
    for entry in new:
        aid = entry.get("attachment_id")
        if aid:
            by_id[aid] = entry
    return list(by_id.values())


def write_json(path: Path, data: Dict[str, Any]) -> None:
    """Write JSON with pretty formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
