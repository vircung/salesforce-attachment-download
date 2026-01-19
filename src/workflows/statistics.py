"""
Statistics Module

Encapsulates workflow statistics data structures and aggregation logic.
Tracks per-CSV and overall statistics across all workflow phases.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Optional

from src.utils import log_section_header

logger = logging.getLogger(__name__)


@dataclass
class CsvFileStatistics:
    """Statistics for a single CSV file."""
    csv_name: str
    records: int
    batches: int
    attachments: int
    downloaded: int
    output_dir: str


@dataclass
class WorkflowStatistics:
    """Aggregated statistics for entire workflow."""
    total_csv_files: int
    total_records: int
    total_batches: int
    total_attachments: int
    per_csv: List[CsvFileStatistics]
    failed_files: List[str]
    failed_downloads: List[Dict[str, Any]]


def create_statistics() -> WorkflowStatistics:
    """Create empty statistics object."""
    return WorkflowStatistics(
        total_csv_files=0,
        total_records=0,
        total_batches=0,
        total_attachments=0,
        per_csv=[],
        failed_files=[],
        failed_downloads=[]
    )


def update_csv_statistics(
    stats: WorkflowStatistics,
    csv_name: str,
    csv_records: int,
    csv_batches: int,
    attachments_found: int,
    attachments_downloaded: int,
    csv_output_dir: Path
) -> None:
    """Update statistics with results from a single CSV file."""
    # Create CsvFileStatistics
    csv_stats = CsvFileStatistics(
        csv_name=csv_name,
        records=csv_records,
        batches=csv_batches,
        attachments=attachments_found,
        downloaded=attachments_downloaded,
        output_dir=str(csv_output_dir)
    )

    # Append to stats.per_csv
    stats.per_csv.append(csv_stats)

    # Update stats totals (total_records, total_batches, total_attachments)
    # Note: total_csv_files is set when initialized
    stats.total_records += csv_records
    stats.total_batches += csv_batches
    stats.total_attachments += attachments_found


def log_workflow_summary(stats: WorkflowStatistics) -> None:
    """Log final workflow summary and statistics."""
    # Use log_section_header("WORKFLOW SUMMARY")
    log_section_header("WORKFLOW SUMMARY")

    # Log each statistic line by line
    logger.info(f"Total CSV files: {stats.total_csv_files}")
    logger.info(f"Total records: {stats.total_records}")
    logger.info(f"Total batches executed: {stats.total_batches}")
    logger.info(f"Total attachments found: {stats.total_attachments}")

    # If failed_downloads, log them
    if stats.failed_downloads:
        logger.warning("\nFailed downloads:")
        for error in stats.failed_downloads:
            logger.warning(f"  - {error['name']} (ID: {error['id']}): {error['error']}")

    # If failed_files, log them
    if stats.failed_files:
        logger.warning(
            f"Failed to process {len(stats.failed_files)} file(s): "
            f"{', '.join(stats.failed_files)}"
        )


def add_failed_csv(stats: WorkflowStatistics, csv_name: str) -> None:
    """Record a CSV that failed processing."""
    stats.failed_files.append(csv_name)


def add_failed_download(
    stats: WorkflowStatistics,
    error: Dict[str, Any]
) -> None:
    """Record a download that failed."""
    stats.failed_downloads.append(error)