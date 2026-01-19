"""
Download Coordinator Module

Orchestrates Phase 3: File download execution.
Manages temp directory lifecycle and executes downloads for all attachment metadata.
"""

import logging
import shutil
from pathlib import Path
from typing import List
from dataclasses import dataclass

from src.download.downloader import download_attachments
from src.api.sf_client import DEFAULT_TMP_DIR_NAME
from src.workflows.directory_manager import get_temp_download_dir, clean_temp_directory
from src.progress.stages import DownloadStage
from src.utils import log_section_header
from src.exceptions import SFAuthError, SFAPIError

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
    download_workers: int,
    batch_size: int,
    download_enabled: bool
) -> List[DownloadResult]:
    """
    Download all attachments from ALL query results sequentially.
    
    This is PHASE 3: For each CSV metadata result, download all attachments.
    Downloads complete for all CSVs before workflow finishes.
    
    Process:
      1. Log phase start
      2. For each QueryResult in query_results:
         - Call coordinate_csv_downloads()
         - Use merged_csv_path from QueryResult
         - Use output_dir/{csv_name}/files/ for downloads
      3. Return list of DownloadResult (one per CSV, in same order)
    
    Args:
        query_results: Results from Phase 2 (contains merged metadata CSVs)
        org_alias: Salesforce org for authentication
        output_dir: Base output directory
        download_stage: Progress stage for downloads
        download_workers: Parallel download workers
        batch_size: Batch size for download workers
        download_enabled: Whether to actually download (True/False)
    
    Returns:
        List[DownloadResult] in same order as query_results
    
    Raises:
        SFAuthError: If auth fails (entire Phase 3 fails)
        SFAPIError: If API error occurs (entire Phase 3 fails)
    """
    log_section_header("PHASE 3: DOWNLOAD ATTACHMENTS")
    
    download_results = []
    total_attachments_all = sum(qr.total_attachments_found for qr in query_results)
    
    if not download_enabled:
        logger.info("Download phase skipped (download=False)")
        download_stage.skip("Download disabled")
        
        # Return skip results for all CSVs
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
    
    if total_attachments_all == 0:
        logger.info("No attachments to download")
        download_stage.skip("No attachments found")
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
    
    # Start download stage
    download_stage.start_downloads(total_attachments_all)
    
    # Download for each CSV
    for csv_idx, query_result in enumerate(query_results, start=1):
        logger.info(f"Downloading CSV {csv_idx}/{len(query_results)}: {query_result.csv_name}")
        
        # Get CSV-specific file output directory
        csv_files_dir = output_dir / query_result.csv_name / 'files'
        
        # Download attachments for this CSV
        result = coordinate_csv_downloads(
            csv_name=query_result.csv_name,
            merged_metadata_csv=query_result.merged_csv_path,
            csv_files_dir=csv_files_dir,
            org_alias=org_alias,
            output_dir=output_dir,
            download_stage=download_stage,
            download_workers=download_workers,
            batch_size=batch_size
        )
        
        download_results.append(result)
    
    # Complete download stage
    total_downloaded = sum(dr.downloaded_count for dr in download_results)
    total_failed = sum(dr.failed_count for dr in download_results)
    total_skipped = sum(dr.skipped_count for dr in download_results)
    
    download_stage.complete(
        f"Downloaded {total_downloaded} files, failed {total_failed}, skipped {total_skipped}"
    )
    
    return download_results


def coordinate_csv_downloads(
    csv_name: str,
    merged_metadata_csv: Path,
    csv_files_dir: Path,
    org_alias: str,
    output_dir: Path,
    download_stage: DownloadStage,
    download_workers: int,
    batch_size: int
) -> DownloadResult:
    """
    Download all attachments for a SINGLE CSV metadata file.
    Manages temp directory lifecycle (create, use, cleanup).
    
    Process:
      1. Create temp directory
      2. Call download_attachments() with metadata CSV
      3. Update download stage
      4. Clean temp directory
      5. Return DownloadResult with counts
    
    Args:
        csv_name: Name of source CSV (for logging)
        merged_metadata_csv: Metadata CSV from Phase 2
        csv_files_dir: Output directory for downloaded files
        org_alias: Salesforce org for authentication
        output_dir: Base output dir (for temp directory path)
        download_stage: Progress stage for updates
        download_workers: Parallel download workers
        batch_size: Batch size for workers
    
    Returns:
        DownloadResult with counts and errors
    
    Raises:
        SFAuthError: If auth fails (propagate to orchestrator)
        SFAPIError: If API error occurs (propagate to orchestrator)
    """
    # Create temp directory
    global_tmp_dir = get_temp_download_dir(output_dir)
    global_tmp_dir.mkdir(parents=True, exist_ok=True)
    
    # Clean temp directory if it has leftovers
    if any(global_tmp_dir.iterdir()):
        shutil.rmtree(global_tmp_dir)
        global_tmp_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        logger.info(f"Downloading {csv_name}: {merged_metadata_csv.name}")
        
        # Call existing downloader
        download_stats = download_attachments(
            metadata_csv=merged_metadata_csv,
            output_dir=csv_files_dir,
            org_alias=org_alias,
            filter_config=None,  # No additional filtering
            progress_stage=download_stage,
            download_workers=download_workers,
            batch_size=batch_size
        )
        
        # Extract results
        downloaded_count = download_stats.get('success', 0)
        skipped_count = download_stats.get('skipped', 0)
        failed_count = download_stats.get('failed', 0)
        errors = download_stats.get('errors', [])
        
        logger.info(
            f"Downloaded: {downloaded_count}, Skipped: {skipped_count}, "
            f"Failed: {failed_count}"
        )
        
        return DownloadResult(
            csv_name=csv_name,
            downloaded_count=downloaded_count,
            skipped_count=skipped_count,
            failed_count=failed_count,
            errors=errors,
            total_attachments=downloaded_count + skipped_count + failed_count
        )
    
    finally:
        # Clean temp directory
        try:
            if global_tmp_dir.exists():
                shutil.rmtree(global_tmp_dir)
                logger.info("Cleaned temp download directory")
        except Exception as e:
            logger.warning(f"Failed to clean temp directory: {e}")