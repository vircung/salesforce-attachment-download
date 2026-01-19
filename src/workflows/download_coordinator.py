"""
Download Coordinator Module

Orchestrates Phase 3: File download execution.
Manages temp directory lifecycle and executes downloads for all attachment metadata.
"""

import logging
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass

from src.download.downloader import download_attachments
from src.progress.stages import DownloadStage
from src.utils import log_section_header
from src.exceptions import SFAuthError, SFAPIError, SFNetworkError
from src.workflows.thread_pool import WorkflowThreadPool

logger = logging.getLogger(__name__)


@dataclass
class DownloadResult:
    """Result of downloading attachments for a single CSV."""
    csv_name: str
    downloaded_count: int
    skipped_count: int
    failed_count: int
    errors: List[dict]
    total_attachments: int


def coordinate_all_downloads(
    query_results: List,  # List[QueryResult] but avoid circular import
    org_alias: str,
    output_dir: Path,
    download_stage: DownloadStage,
    thread_pool: WorkflowThreadPool,
    download_enabled: bool = True
) -> List[DownloadResult]:
    """
    Coordinate download of all attachments across all CSVs.
    
    Uses thread pool for execution.
    
    Args:
        query_results: List of query results (one per CSV)
        org_alias: Salesforce org alias
        output_dir: Base output directory
        download_stage: Progress tracking stage (must be pre-initialized)
        thread_pool: Thread pool for execution
        download_enabled: Whether to actually download files
    
    Returns:
        List of DownloadResult objects (one per CSV)
    
    Raises:
        SFNetworkError: If network error occurs during download
        SFAuthError: If authentication fails
        SFAPIError: If API error occurs
    """
    log_section_header("PHASE 3: DOWNLOAD ATTACHMENTS")
    
    download_results = []
    
    # Calculate global total ONCE
    total_attachments_all = sum(qr.total_attachments_found for qr in query_results)
    
    # Initialize progress ONCE with global total (coordinator's responsibility)
    download_stage.start_downloads(total_attachments_all)
    
    # Early return: downloads disabled
    if not download_enabled:
        logger.info("Download phase skipped (download=False)")
        download_stage.complete("Download disabled")
        
        for query_result in query_results:
            download_results.append(DownloadResult(
                csv_name=query_result.csv_name,
                downloaded_count=0,
                skipped_count=query_result.total_attachments_found,
                failed_count=0,
                errors=[],
                total_attachments=0
            ))
        return download_results
    
    # Early return: no attachments
    if total_attachments_all == 0:
        logger.info("No attachments to download")
        download_stage.complete("No attachments found")
        return [
            DownloadResult(
                csv_name=qr.csv_name,
                downloaded_count=0,
                skipped_count=0,
                failed_count=0,
                errors=[],
                total_attachments=0
            )
            for qr in query_results
        ]
    
    # Execute downloads: always use thread pool
    logger.info(f"Downloading {total_attachments_all} attachments with {thread_pool.config.query_workers} workers")
    
    # Clear any leftover results from previous phases
    thread_pool.clear_results()
    
    # Submit all CSV downloads to thread pool
    for query_result in query_results:
        csv_files_dir = output_dir / query_result.csv_name / 'files'
        
        thread_pool.submit_task(
            task_id=f"download_{query_result.csv_name}",
            fn=download_attachments,
            args=(
                query_result.merged_csv_path,      # metadata_csv
                csv_files_dir,                      # output_dir
                org_alias,                          # org_alias
                None,                               # filter_config
                download_stage                      # progress_stage (NO INIT!)
            )
        )
    
    # Wait for all downloads to complete
    worker_results = thread_pool.wait_for_completion(phase_name="download")
    
    # Check for failures
    failed_tasks = [wr for wr in worker_results if not wr.success]
    if failed_tasks:
        error_details = [f"{wr.task_id}: {wr.error}" for wr in failed_tasks]
        error_msg = f"Download phase failed: {len(failed_tasks)} CSV(s) failed\n" + "\n".join(error_details)
        download_stage.fail(error_msg)
        raise SFAPIError(error_msg)
    
    # Convert worker results to DownloadResult
    for worker_result in worker_results:
        if worker_result.result is None:
            continue  # Skip if no result
        stats = worker_result.result
        csv_name = worker_result.task_id.replace("download_", "")
        
        download_results.append(DownloadResult(
            csv_name=csv_name,
            downloaded_count=stats['success'],
            skipped_count=stats['skipped'],
            failed_count=stats['failed'],
            errors=stats['errors'],
            total_attachments=stats['total']
        ))
    
    # Aggregate final stats
    total_downloaded = sum(dr.downloaded_count for dr in download_results)
    total_failed = sum(dr.failed_count for dr in download_results)
    total_skipped = sum(dr.skipped_count for dr in download_results)
    
    # Complete progress with summary
    download_stage.complete(
        f"Downloaded {total_downloaded} files, failed {total_failed}, skipped {total_skipped}"
    )
    
    logger.info(f"Download phase complete: {total_downloaded} downloaded, {total_failed} failed, {total_skipped} skipped")
    
    return download_results