"""
Workflow Orchestrator Module

Main entry point for the three-phase Salesforce attachment workflow.
Orchestrates CSV processing, SOQL querying, and file downloads.
Simplified orchestration layer that delegates to specialized coordinators.
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import asdict

from src.utils import log_section_header
from src.progress.core import ProgressTracker
from src.progress.stages import CsvProcessingStage, SoqlQueryStage, DownloadStage
from src.progress.core.stage import StageStatus
from src.exceptions import SFAuthError, SFQueryError, SFAPIError
from src.workflows.exception_handler import WorkflowExceptionHandler
from src.constants import WorkflowPhase

# Coordinators
from src.workflows.csv_coordinator import coordinate_csv_processing
from src.workflows.query_coordinator import execute_all_csv_queries
from src.workflows.download_coordinator import coordinate_all_downloads, DownloadResult

# Support modules
from src.workflows.directory_manager import create_csv_directories
from src.workflows.error_handler import WorkflowErrorHandler

# Thread pool support
from src.workflows.thread_pool import ThreadPoolConfig, WorkflowThreadPool

logger = logging.getLogger(__name__)


def process(
    org_alias: str,
    output_dir: Path,
    records_dir: Path,
    batch_size: int = 100,
    download: bool = True,
    progress_tracker: Optional[ProgressTracker] = None,
    workers: int = 2
) -> Dict[str, Any]:
    """
    Main entry point: orchestrate three-phase workflow.
    
    Phases:
      1. CSV Processing: Discover all CSVs, extract record batches
      2. SOQL Querying: Execute batch queries for all CSVs
      3. Downloads: Download all attachments for all CSVs
    
    All CSV processing completes before queries begin.
    All queries complete before downloads begin.
    
    Args:
        org_alias: Salesforce org alias for authentication
        output_dir: Base output directory (subdirectories per CSV)
        records_dir: Directory containing input CSV files
        batch_size: ParentIds per SOQL query (default: 100)
        download: Whether to download files (default: True)
        progress_tracker: Optional progress tracker for UI updates
        workers: Parallel workers for queries and downloads (default: 2)
    
    Returns:
        Dictionary with final statistics:
        {
            'total_csv_files': int,
            'total_records': int,
            'total_batches': int,
            'total_attachments': int,
            'per_csv': [
                {
                    'csv_name': str,
                    'records': int,
                    'batches': int,
                    'attachments': int,
                    'downloaded': int,
                    'output_dir': str
                },
                ...
            ]
        }
    
    Raises:
        FileNotFoundError: If records_dir doesn't exist
        ValueError: If no CSVs found or validation fails
        SFAuthError: If authentication fails (fatal)
        SFQueryError: If query fails (fatal)
        SFAPIError: If API error occurs (fatal)
    """
    logger.info(f"Org: {org_alias}")
    logger.info(f"Records directory: {records_dir.absolute()}")
    logger.info(f"Output directory: {output_dir.absolute()}")
    logger.info(f"Batch size: {batch_size}")
    logger.info(f"Download enabled: {download}")
    logger.info(f"Workers: {workers}")
    
    try:
        # Initialize progress stages
        csv_stage = CsvProcessingStage()
        soql_stage = SoqlQueryStage()
        download_stage = DownloadStage()
        
        # Add to tracker if provided
        if progress_tracker:
            progress_tracker.add_stage(csv_stage)
            progress_tracker.add_stage(soql_stage)
            progress_tracker.add_stage(download_stage)
        
        # Initialize error handler
        error_handler = WorkflowErrorHandler(csv_stage, soql_stage, download_stage)
        
        # Create thread pool configuration and context manager
        thread_pool_config = ThreadPoolConfig(query_workers=workers)
        thread_pool = WorkflowThreadPool(thread_pool_config)
        logger.debug(f"Created thread pool: workers={workers}")
        
        # ============================================================
        # PHASE 1: CSV PROCESSING
        # ============================================================
        log_section_header(WorkflowPhase.CSV_PROCESSING)
        try:
            csv_records = coordinate_csv_processing(
                records_dir=records_dir,
                batch_size=batch_size,
                csv_stage=csv_stage,
                progress_tracker=progress_tracker
            )
            
            # Pre-populate SOQL stage total for Phase 2
            total_batches = sum(csv_info.total_batches for csv_info in csv_records)
            if total_batches > 0 and soql_stage:
                soql_stage.set_total(total_batches)
                logger.debug(f"Pre-populated SOQL stage total: {total_batches} batches")
            
            # Mark CSV stage as completed after Phase 1
            csv_stage.complete(f"Processed {len(csv_records)} CSV files")
        except Exception as e:
            error_handler.handle_csv_error("csv_discovery", e)
            raise
        
        # ============================================================
        # PHASE 2: SOQL QUERYING (ALL CSVs)
        # ============================================================
        log_section_header(WorkflowPhase.SOQL_QUERYING)
        try:
            with thread_pool:
                query_results = execute_all_csv_queries(
                    csv_records=csv_records,
                    org_alias=org_alias,
                    output_dir=output_dir,
                    soql_stage=soql_stage,
                    thread_pool=thread_pool
                )
                
                # Pre-populate Download stage total for Phase 3
                total_attachments = sum(qr.total_attachments_found for qr in query_results)
                if total_attachments > 0 and download_stage:
                    download_stage.set_total(total_attachments)
                    logger.debug(f"Pre-populated Download stage total: {total_attachments} attachments")
                    
                # ============================================================
                # PHASE 3: DOWNLOADS (ALL CSVs)
                # ============================================================
                log_section_header(WorkflowPhase.DOWNLOADS)
                download_results = []
                download_results = coordinate_all_downloads(
                    query_results=query_results,
                    org_alias=org_alias,
                    output_dir=output_dir,
                    download_stage=download_stage,
                    thread_pool=thread_pool,
                    download_enabled=download
                )
        except Exception as e:
            error_handler.handle_query_error("all_queries", e)
            raise
        
        # ============================================================
        # FINALIZE & AGGREGATE STATISTICS
        # ============================================================
        log_section_header(WorkflowPhase.SUMMARY)
        
        # Build statistics inline
        csv_dirs = []
        for csv_info in csv_records:
            dirs = create_csv_directories(output_dir, csv_info.csv_name)
            csv_dirs.append(dirs.csv_output_dir)
        
        stats = {
            'total_csv_files': len(csv_records),
            'total_records': sum(csv_info.total_records for csv_info in csv_records),
            'total_batches': sum(csv_info.total_batches for csv_info in csv_records),
            'total_attachments': sum(qr.total_attachments_found for qr in query_results),
            'per_csv': [
                {
                    'csv_name': csv_info.csv_name,
                    'records': csv_info.total_records,
                    'batches': csv_info.total_batches,
                    'attachments': qr.total_attachments_found,
                    'downloaded': dr.downloaded_count,
                    'output_dir': str(csv_dir)
                }
                for csv_info, qr, dr, csv_dir in zip(csv_records, query_results, download_results, csv_dirs)
            ]
        }
        
        # Mark stages as complete
        csv_stage.complete(f"Processed {len(csv_records)} CSV files")
        soql_stage.complete(f"Completed {stats['total_batches']} batches")
        download_stage.complete(f"Downloaded {stats['total_attachments']} attachments")
        
        # Log final summary
        log_section_header(WorkflowPhase.SUMMARY)
        logger.info(f"Total CSV files: {stats['total_csv_files']}")
        logger.info(f"Total records: {stats['total_records']}")
        logger.info(f"Total batches executed: {stats['total_batches']}")
        logger.info(f"Total attachments found: {stats['total_attachments']}")
        
        # Return statistics as dictionary
        return stats
    
    except SFAuthError as e:
        WorkflowExceptionHandler.handle_and_log(e)
        raise
    
    except SFQueryError as e:
        WorkflowExceptionHandler.handle_and_log(e)
        raise
    
    except SFAPIError as e:
        WorkflowExceptionHandler.handle_and_log(e)
        raise
    
    except Exception as e:
        logger.error(f"Unexpected workflow error: {e}")
        logger.debug("Full error details:", exc_info=True)
        raise