#!/usr/bin/env python3
"""
Verify downloaded files against execution report.

Reads report_downloaded.json, checks each file exists on disk,
and moves missing entries to report_missing.json.
"""

import argparse
import json
import sys
from pathlib import Path

from src.report.writer import (
    REPORT_DOWNLOADED, REPORT_MISSING, read_report, write_json, merge_entries,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify downloaded files against execution report"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path("./output"),
        help="Output directory containing reports and downloaded files (default: ./output)",
    )
    parser.add_argument(
        "--redownload",
        action="store_true",
        help="Attempt to re-download missing files (not yet implemented)",
    )
    args = parser.parse_args()

    if args.redownload:
        print("--redownload is not yet implemented")
        return 1

    output_dir = args.output
    downloaded_path = output_dir / REPORT_DOWNLOADED
    missing_path = output_dir / REPORT_MISSING

    if not downloaded_path.exists():
        print(f"No report found: {downloaded_path}")
        return 1

    downloaded_report = read_report(downloaded_path)
    missing_report = read_report(missing_path)

    entries = downloaded_report.get("entries", [])
    existing_missing = missing_report.get("entries", [])

    still_present = []
    newly_missing = []

    for entry in entries:
        obj_name = entry.get("object_name", "")
        filename = entry.get("filename", "")
        file_path = output_dir / obj_name / filename

        if file_path.exists():
            still_present.append(entry)
        else:
            # Mark as missing with VerifyMissing error
            entry_copy = dict(entry)
            entry_copy["error"] = "file not found on disk"
            entry_copy["error_type"] = "VerifyMissing"
            newly_missing.append(entry_copy)

    # Merge newly missing with existing missing entries
    merged_missing = merge_entries(existing_missing, newly_missing)

    # Update summaries
    all_objects = sorted(set(
        e.get("object_name", "") for e in still_present + merged_missing
        if e.get("object_name")
    ))

    total_queried = downloaded_report.get("summary", {}).get("total_queried", 0)

    # Rebuild downloaded report
    dl_report = {
        "generated_at": downloaded_report.get("generated_at", ""),
        "instance_url": downloaded_report.get("instance_url", ""),
        "output_dir": downloaded_report.get("output_dir", str(output_dir.resolve())),
        "summary": {
            "total_queried": total_queried,
            "downloaded": len(still_present),
            "missing": len(merged_missing),
            "objects": all_objects,
        },
        "stages": downloaded_report.get("stages", {}),
        "entries": still_present,
    }

    # Rebuild missing report
    ms_report = {
        "generated_at": downloaded_report.get("generated_at", ""),
        "instance_url": downloaded_report.get("instance_url", ""),
        "output_dir": downloaded_report.get("output_dir", str(output_dir.resolve())),
        "summary": {
            "total_queried": total_queried,
            "downloaded": len(still_present),
            "missing": len(merged_missing),
            "objects": all_objects,
        },
        "stages": downloaded_report.get("stages", {}),
        "entries": merged_missing,
    }

    write_json(downloaded_path, dl_report)
    write_json(missing_path, ms_report)

    print(f"Verified: {len(still_present)} files")
    if newly_missing:
        print(f"Missing: {len(newly_missing)} files")
        for entry in newly_missing:
            print(f"  - {entry.get('object_name', '')}/{entry.get('filename', '')}")
        print(f"Updated {REPORT_DOWNLOADED} and {REPORT_MISSING}")
        return 1
    else:
        print("All files present")
        return 0


if __name__ == "__main__":
    sys.exit(main())
