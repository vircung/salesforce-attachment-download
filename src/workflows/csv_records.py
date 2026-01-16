"""
CSV Records Workflow Module

High-level workflow for processing CSV files containing record IDs
and downloading their associated attachments.
"""

import csv
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from src.query.executor import run_query_script_with_filter
from src.query.filters import ParentIdFilter, build_soql_where_clause
from src.csv.processor import process_records_directory
from src.download.downloader import download_attachments
from src.api.sf_client import DEFAULT_TMP_DIR_NAME
from src.utils import log_section_header
from src.workflows.common import (
    ensure_directories,
    merge_csv_files
)
from src.exceptions import SFQueryError, SFAuthError, SFAPIError
from src.progress.core import ProgressTracker
from src.progress.core.stage import StageStatus
from src.progress.stages import CsvProcessingStage, SoqlQueryStage, DownloadStage

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

    This workflow:
    1. Discovers CSV files in records_dir
    2. Extracts record IDs from each CSV's 'Id' column
    3. Batches IDs (default: 100 per batch) to respect SOQL length limits
    4. Queries attachments for each batch using WHERE ParentId IN (...)
    5. Downloads attachments organized by CSV filename

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

    # Start CSV processing stage
    csv_stage.start_discovery(records_dir)
    
    # Process CSV files - validates, extracts IDs, creates batches
    csv_records = process_records_directory(records_dir, batch_size)
    
    # Update CSV stage with discovery results
    csv_stage.update_discovery(len(csv_records))
    csv_stage.start_processing(len(csv_records))
    total_records_found = sum(csv_info.total_records for csv_info in csv_records)
    csv_stage.update_processing(
        completed_files=0,
        total_records=total_records_found
    )
    
    # Calculate total batches across all CSV files for SOQL stage initialization
    total_batches_all_csvs = sum(csv_info.total_batches for csv_info in csv_records)
    
    # Start SOQL stage with total batch count
    soql_stage.start_querying(total_batches_all_csvs)
    if total_batches_all_csvs == 0:
        soql_stage.complete("No batches to query")

    # Statistics tracking
    stats = {
        'total_csv_files': len(csv_records),
        'total_records': 0,
        'total_batches': 0,
        'total_attachments': 0,
        'per_csv': []
    }

    failed_files = []
    failed_downloads = []
    
    # Track cumulative batches across all CSV files for SOQL progress
    cumulative_batches_completed = 0

    # Process each CSV file
    for csv_idx, csv_info in enumerate(csv_records, start=1):
        log_section_header(f"PROCESSING CSV {csv_idx}/{len(csv_records)}: {csv_info.csv_name}.csv")
        logger.info(f"Records: {csv_info.total_records}")
        logger.info(f"Batches: {csv_info.total_batches}")
        
        # Update CSV processing progress
        if csv_stage.progress.status != StageStatus.COMPLETED:
            csv_stage.update_processing(
                completed_files=csv_idx,
                current_csv=csv_info.csv_name,
                current_records=csv_info.total_records
            )

        try:
            # Create output subdirectories for this CSV
            csv_output_dir = output_dir / csv_info.csv_name
            csv_metadata_dir = csv_output_dir / 'metadata'
            csv_files_dir = csv_output_dir / 'files'

            ensure_directories(csv_metadata_dir, csv_files_dir)

            logger.info(f"Output directories:")
            logger.info(f"  Metadata: {csv_metadata_dir}")
            logger.info(f"  Files: {csv_files_dir}")
            
            # Update SOQL stage to show current CSV being processed (don't reset totals)
            soql_stage.update_progress(
                message=f"Processing {csv_info.csv_name} ({csv_info.total_batches} batches)",
                details={
                    "current_csv": csv_info.csv_name,
                    "csv_batches": csv_info.total_batches
                }
            )

            # Query attachments for each batch
            batch_csv_paths = []
            total_attachments = 0

            for batch_idx, id_batch in enumerate(csv_info.id_batches):
                logger.info(f"Batch {batch_idx + 1}/{csv_info.total_batches}: Querying {len(id_batch)} ParentId(s)")
                
                # Update SOQL stage progress with cumulative tracking
                soql_stage.update_batch(
                    completed_batches=cumulative_batches_completed + batch_idx,
                    current_batch=cumulative_batches_completed + batch_idx + 1,
                    batch_size=len(id_batch)
                )

                # Build WHERE clause using existing filters module
                filter_config = ParentIdFilter(
                    prefixes=[],
                    exact_ids=id_batch,
                    strategy='soql'
                )
                where_clause = build_soql_where_clause(filter_config)

                # Query attachments for this batch
                batch_csv_path = run_query_script_with_filter(
                    org_alias=org_alias,
                    output_dir=csv_metadata_dir,
                    where_clause=where_clause
                )

                batch_csv_paths.append(batch_csv_path)

                # Count rows in batch (quick check without full read)
                with batch_csv_path.open('r', encoding='utf-8') as f:
                    batch_count = sum(1 for _ in csv.DictReader(f))
                    total_attachments += batch_count
                    logger.info(f"Batch {batch_idx + 1}/{csv_info.total_batches}: Found {batch_count} attachment(s)")

                # Complete this batch in SOQL stage with cumulative tracking
                soql_stage.complete_batch(
                    batch_num=cumulative_batches_completed + batch_idx + 1,
                    records_found=batch_count,
                    total_attachments=stats['total_attachments'] + total_attachments  # Overall total
                )

                if cumulative_batches_completed + batch_idx + 1 == total_batches_all_csvs:
                    soql_stage.complete(
                        f"Completed {total_batches_all_csvs} batches, found {stats['total_attachments'] + total_attachments} attachments"
                    )

                

            # Merge all batch results into single CSV
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            merged_csv_path = csv_metadata_dir / f"attachments_{timestamp}_merged.csv"

            merged_count = merge_csv_files(batch_csv_paths, merged_csv_path)
            
            # Refresh SOQL stage before downloads
            soql_stage.update_progress(
                message=f"SOQL complete for {csv_info.csv_name}; starting downloads",
                details={
                    "current_csv": csv_info.csv_name,
                    "current_batch": cumulative_batches_completed + csv_info.total_batches,
                    "total_attachments": stats['total_attachments'] + merged_count
                }
            )

            # Download attachments if enabled

            downloaded_count = 0
            if download and merged_count > 0:
                logger.info(f"Downloading {merged_count} attachment(s) to: {csv_files_dir}")

                global_tmp_download_dir = output_dir / DEFAULT_TMP_DIR_NAME
                try:
                    global_tmp_download_dir.mkdir(parents=True, exist_ok=True)

                    # Clean global temp dir before each CSV download phase.
                    if any(global_tmp_download_dir.iterdir()):
                        shutil.rmtree(global_tmp_download_dir)
                        global_tmp_download_dir.mkdir(parents=True, exist_ok=True)

                    download_stats = download_attachments(
                        metadata_csv=merged_csv_path,
                        output_dir=csv_files_dir,
                        org_alias=org_alias,
                        filter_config=None,  # No additional filtering needed
                        progress_stage=download_stage,
                        download_workers=download_workers,
                        batch_size=batch_size
                    )

                    downloaded_count = download_stats['success']
                    skipped_count = download_stats.get('skipped', 0)
                    failed_count = download_stats.get('failed', 0)
                    errors = download_stats.get('errors', [])

                    logger.info(
                        f"Downloaded: {downloaded_count}, Skipped: {skipped_count}, Failed: {failed_count}, "
                        f"Total: {merged_count} file(s)"
                    )

                    # Complete download stage
                    download_stage.complete_downloads(
                        total_downloaded=downloaded_count,
                        total_failed=failed_count,
                        total_skipped=skipped_count
                    )

                    if errors:
                        failed_downloads.extend(errors)

                except SFAuthError as e:
                    logger.error(f"Download failed for {csv_info.csv_name}: {e}")
                    download_stage.fail(str(e), f"Download failed for {csv_info.csv_name}")
                    raise

                except SFAPIError as e:
                    logger.error(f"Download failed for {csv_info.csv_name}: {e}")
                    download_stage.fail(str(e), f"Download failed for {csv_info.csv_name}")
                    raise

                except Exception as e:
                    logger.error(f"Download failed for {csv_info.csv_name}: {e}")
                    download_stage.fail(str(e), f"Download failed for {csv_info.csv_name}")
                    # Continue processing other CSVs even if download fails

                finally:
                    try:
                        if global_tmp_download_dir.exists():
                            shutil.rmtree(global_tmp_download_dir)
                    except Exception:
                        pass
            elif download and merged_count == 0:
                logger.info("No attachments to download")
                download_stage.skip("No attachments to download")
            else:
                logger.info("Download skipped (download=False)")
                download_stage.skip("Download disabled")

            # Record statistics for this CSV
            csv_stats = {
                'csv_name': csv_info.csv_name,
                'records': csv_info.total_records,
                'batches': csv_info.total_batches,
                'attachments': merged_count,
                'downloaded': downloaded_count,
                'output_dir': str(csv_output_dir)
            }
            stats['per_csv'].append(csv_stats)
            stats['total_records'] += csv_info.total_records
            stats['total_batches'] += csv_info.total_batches
            stats['total_attachments'] += merged_count

            logger.info(f"✓ Completed {csv_info.csv_name}.csv")
            
            # Update cumulative batch counter for next CSV
            cumulative_batches_completed += csv_info.total_batches
            
            # Update CSV stage progress to reflect completion of this file
            csv_stage.update_processing(
                completed_files=csv_idx,  # Increment to current file number
                current_csv=csv_info.csv_name,
                current_records=csv_info.total_records,
                total_records=stats['total_records']
            )
            

        except SFAuthError as e:
            logger.error(f"✗ Salesforce authentication failed for {csv_info.csv_name}.csv: {e}")
            logger.error("Please check your Salesforce CLI authentication (run: sf org list)")
            logger.debug("Full error details:", exc_info=True)
            failed_files.append(csv_info.csv_name)
            
            # Mark stages as failed
            csv_stage.fail(str(e))
            soql_stage.fail(str(e))
            download_stage.fail(str(e))
            
            # Stop workflow on auth errors
            raise
        except SFQueryError as e:
            logger.error(f"✗ Query failed for {csv_info.csv_name}.csv: {e}")
            logger.error("Check query syntax and record IDs")
            logger.debug("Full error details:", exc_info=True)
            failed_files.append(csv_info.csv_name)
            csv_stage.fail(str(e))
            soql_stage.fail(str(e))
            
        except SFAPIError as e:
            logger.error(f"✗ Salesforce API error for {csv_info.csv_name}.csv: {e}")
            logger.error("Check network connection and API access")
            logger.debug("Full error details:", exc_info=True)
            failed_files.append(csv_info.csv_name)
            csv_stage.fail(str(e))
            download_stage.fail(str(e))
            
            # Stop workflow on fatal API/network errors
            raise

        except FileNotFoundError as e:
            logger.error(f"✗ File not found while processing {csv_info.csv_name}.csv: {e}")
            logger.debug("Full error details:", exc_info=True)
            failed_files.append(csv_info.csv_name)
            csv_stage.fail(str(e))
            
        except PermissionError as e:
            logger.error(f"✗ Permission denied while processing {csv_info.csv_name}.csv: {e}")
            logger.debug("Full error details:", exc_info=True)
            failed_files.append(csv_info.csv_name)
            csv_stage.fail(str(e))
            
        except ValueError as e:
            logger.error(f"✗ Invalid data in {csv_info.csv_name}.csv: {e}")
            logger.debug("Full error details:", exc_info=True)
            failed_files.append(csv_info.csv_name)
            csv_stage.fail(str(e))
            
        except KeyboardInterrupt:
            logger.warning(f"\n✗ Processing interrupted by user during {csv_info.csv_name}.csv")
            raise  # Re-raise to be caught by main
            
        except Exception as e:
            logger.error(f"✗ Unexpected error processing {csv_info.csv_name}.csv: {e}")
            logger.error("See log file for detailed error information")
            logger.debug("Full error details:", exc_info=True)
            failed_files.append(csv_info.csv_name)
            csv_stage.fail(str(e))
            
            # Continue processing other CSV files

    # Ensure SOQL stage reflects completion before summary
    if soql_stage.progress.status == StageStatus.RUNNING:
        soql_stage.complete(
            f"Completed {stats['total_batches']} batches, found {stats['total_attachments']} attachments"
        )

    # Final summary
    log_section_header("WORKFLOW SUMMARY")
    logger.info(f"Total CSV files: {stats['total_csv_files']}")
    logger.info(f"Total records: {stats['total_records']}")
    logger.info(f"Total batches executed: {stats['total_batches']}")
    logger.info(f"Total attachments found: {stats['total_attachments']}")

    if failed_downloads:
        logger.warning("\nFailed downloads:")
        for error in failed_downloads:
            logger.warning(f"  - {error['name']} (ID: {error['id']}): {error['error']}")

    # Complete stages BEFORE returning (before progress tracker context exits)
    # Always complete stages appropriately regardless of partial failures
    if failed_files:
        logger.warning(f"Failed to process {len(failed_files)} file(s): {', '.join(failed_files)}")
        
        # If some files failed but we processed others successfully
        if stats['total_batches'] > 0:
            # CSV stage partially succeeded
            if csv_stage.progress.status != StageStatus.COMPLETED:
                csv_stage.complete(f"Processed {stats['total_csv_files'] - len(failed_files)}/{stats['total_csv_files']} CSV files")
            # SOQL stage succeeded for processed files
            if soql_stage.progress.status != StageStatus.COMPLETED:
                soql_stage.complete(f"Completed {stats['total_batches']} batches, found {stats['total_attachments']} attachments")
        else:
            # No batches were processed successfully
            if csv_stage.progress.status != StageStatus.COMPLETED:
                csv_stage.fail(f"Failed to process {len(failed_files)} file(s)")
            if soql_stage.progress.status != StageStatus.COMPLETED:
                soql_stage.fail(f"Failed to process any files: {', '.join(failed_files)}")
    else:
        logger.info("All CSV files processed successfully!")
        # Mark both stages as complete with final progress update
        if csv_stage.progress.status != StageStatus.COMPLETED:
            csv_stage.complete(f"Processed {stats['total_csv_files']} CSV files")
        if soql_stage.progress.status != StageStatus.COMPLETED:
            soql_stage.complete(f"Completed {stats['total_batches']} batches, found {stats['total_attachments']} attachments")

    

    return stats
