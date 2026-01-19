"""
CSV Records Workflow Module

High-level workflow for processing CSV files containing record IDs
and downloading their associated attachments.
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional

from src.workflows.csv_coordinator import coordinate_csv_processing
from src.workflows.query_coordinator import execute_all_csv_queries
from src.workflows.download_coordinator import coordinate_all_downloads
from src.progress.core import ProgressTracker
from src.progress.stages import CsvProcessingStage, SoqlQueryStage, DownloadStage
from src.utils import log_section_header

logger = logging.getLogger(__name__)


def process_csv_records_workflow(
    org_alias: str,
    output_dir: Path,
    records_dir: Path,
    batch_size: int = 100,
    download: bool = True,
    progress_tracker: Optional[ProgressTracker] = None,
    download_workers: int = 1
) -> Dict[str, Any]:
    """
    Process CSV files containing record IDs and download their attachments.
    
    This workflow uses three-phase coordinators:
    1. CSV Coordinator: Discover and batch CSVs
    2. Query Coordinator: Execute SOQL queries for all CSVs
    3. Download Coordinator: Download attachments for all CSVs

    Args:
        org_alias: Salesforce org alias for authentication
        output_dir: Base output directory (subdirectories created per CSV)
        records_dir: Directory containing CSV files with record IDs
        batch_size: Number of ParentIds per SOQL query (default: 100)
        download: Whether to download files after querying (default: True)
        progress_tracker: Optional progress tracker for UI updates
        download_workers: Parallel downloads per bucket (default: 1)

    Returns:
        Dictionary with processing statistics:
        {
            'total_csv_files': int,
            'total_records': int,
            'total_batches': int,
            'total_attachments': int,
            'per_csv': [{'csv_name': str, 'records': int, ...}, ...]
        }

    Raises:
        FileNotFoundError: If records_dir doesn't exist
        ValueError: If no CSV files found or CSV missing 'Id' column
        RuntimeError: If query or download fails
        SFAuthError: If authentication fails (fatal)
        SFAPIError: If network/service errors occur (fatal)
    """
    logger.info(f"Org: {org_alias}")
    logger.info(f"Records directory: {records_dir.absolute()}")
    logger.info(f"Output directory: {output_dir.absolute()}")
    logger.info(f"Batch size: {batch_size}")
    logger.info(f"Download enabled: {download}")
    logger.info(f"Download workers: {download_workers}")

    # Initialize progress stages
    csv_stage = CsvProcessingStage()
    soql_stage = SoqlQueryStage() 
    download_stage = DownloadStage()
    
    # Add stages to tracker if provided
    if progress_tracker:
        progress_tracker.add_stage(csv_stage)
        progress_tracker.add_stage(soql_stage)
        progress_tracker.add_stage(download_stage)

    # PHASE 1: CSV Discovery and Processing
    csv_records = coordinate_csv_processing(
        records_dir=records_dir,
        batch_size=batch_size,
        csv_stage=csv_stage,
        progress_tracker=progress_tracker
    )

    # PHASE 2: SOQL Batch Querying
    query_results = execute_all_csv_queries(
        csv_records=csv_records,
        org_alias=org_alias,
        output_dir=output_dir,
        soql_stage=soql_stage,
        batch_size=batch_size
    )

    # PHASE 3: Download Attachments
    download_results = coordinate_all_downloads(
        query_results=query_results,
        org_alias=org_alias,
        output_dir=output_dir,
        download_stage=download_stage,
        download_workers=download_workers,
        batch_size=batch_size,
        download_enabled=download
    )

    # Build statistics from results
    stats = {
        'total_csv_files': len(csv_records),
        'total_records': sum(csv_info.total_records for csv_info in csv_records),
        'total_batches': sum(csv_info.total_batches for csv_info in csv_records),
        'total_attachments': sum(qr.total_attachments_found for qr in query_results),
        'per_csv': []
    }

    # Build per-CSV statistics
    for csv_record, query_result, download_result in zip(csv_records, query_results, download_results):
        csv_stats = {
            'csv_name': csv_record.csv_name,
            'records': csv_record.total_records,
            'batches': csv_record.total_batches,
            'attachments': query_result.total_attachments_found,
            'downloaded': download_result.downloaded_count,
            'output_dir': str(output_dir / csv_record.csv_name)
        }
        stats['per_csv'].append(csv_stats)

    # Final summary
    log_section_header("WORKFLOW SUMMARY")
    logger.info(f"Total CSV files: {stats['total_csv_files']}")
    logger.info(f"Total records: {stats['total_records']}")
    logger.info(f"Total batches executed: {stats['total_batches']}")
    logger.info(f"Total attachments found: {stats['total_attachments']}")

    total_downloaded = sum(dr.downloaded_count for dr in download_results)
    total_failed = sum(dr.failed_count for dr in download_results)
    total_skipped = sum(dr.skipped_count for dr in download_results)
    
    if download:
        logger.info(f"Total downloaded: {total_downloaded}")
        logger.info(f"Total failed: {total_failed}")
        logger.info(f"Total skipped: {total_skipped}")
    else:
        logger.info("Downloads were skipped (--download=False)")

    # Check for any errors
    failed_downloads = []
    for dr in download_results:
        failed_downloads.extend(dr.errors)

    if failed_downloads:
        logger.warning("\nFailed downloads:")
        for error in failed_downloads:
            logger.warning(f"  - {error.get('name', 'Unknown')} (ID: {error.get('id', 'Unknown')}): {error.get('error', 'Unknown error')}")

    logger.info("All CSV files processed successfully!")

    return stats
