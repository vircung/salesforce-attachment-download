"""
CSV Coordinator Module

Orchestrates Phase 1: CSV discovery and batch processing.
Responsible for discovering all CSV files and preparing them for querying.
"""

import logging
from pathlib import Path
from typing import List, Optional
from src.constants import CsvRecordInfo, WorkflowPhase
from src.csv.utils import process_records_directory
from src.progress.stages import CsvProcessingStage
from src.progress.core import ProgressTracker
from src.utils import log_section_header

logger = logging.getLogger(__name__)


def coordinate_csv_processing(
    records_dir: Path,
    batch_size: int,
    csv_stage: CsvProcessingStage,
    progress_tracker: Optional[ProgressTracker] = None
) -> List[CsvRecordInfo]:
    """
    Discover and process all CSV files in one phase.
    
    This is PHASE 1: Discovers all CSV files, validates them, 
    extracts record IDs, and creates batches for querying.
    
    Process:
      1. Log phase start
      2. Start CSV discovery in stage
      3. Call process_records_directory() to discover and batch CSVs
      4. Initialize CSV stage with discovery results
      5. Return list of CsvRecordInfo ready for Phase 2
    
    Args:
        records_dir: Directory containing CSV files
        batch_size: Number of IDs per batch
        csv_stage: Progress stage for CSV processing
        progress_tracker: Optional tracker (not used in this phase but for consistency)
    
    Returns:
        List[CsvRecordInfo] containing all CSVs with batches ready for querying
    
    Raises:
        FileNotFoundError: If records_dir doesn't exist
        ValueError: If no CSV files found or missing 'Id' column
    """
    log_section_header(WorkflowPhase.CSV_PROCESSING)
    logger.info("Starting CSV discovery...")

    # Start discovery stage
    csv_stage.start_discovery(records_dir)
    
    # Quick scan for initial estimate before full discovery
    estimated_files = csv_stage.estimate_total_files(records_dir)
    if estimated_files > 0:
        csv_stage.set_processing_total(estimated_files)
        logger.debug(f"Pre-populated CSV stage total: {estimated_files} files estimated")
    
    # Call existing processor to discover and process CSVs
    csv_records = process_records_directory(records_dir, batch_size)
    
    # Update CSV stage with discovery results
    initialize_csv_stage(csv_stage, csv_records)
    
    # Log summary
    total_records = sum(csv_info.total_records for csv_info in csv_records)
    total_batches = sum(csv_info.total_batches for csv_info in csv_records)
    logger.info(
        f"Discovered {len(csv_records)} CSV files with {total_records} "
        f"total records in {total_batches} batches"
    )
    
    return csv_records


def initialize_csv_stage(
    csv_stage: CsvProcessingStage,
    csv_records: List[CsvRecordInfo]
) -> None:
    """
    Initialize CSV stage with discovery results.
    
    Updates the stage with:
    - Total CSV count discovered
    - Total record count across all CSVs
    - Total batch count across all CSVs
    
    Args:
        csv_stage: Progress stage to update
        csv_records: List of discovered CSVs
    """
    # Update discovery with total CSV count
    csv_stage.update_discovery(len(csv_records))
    
    # Calculate totals
    total_records = sum(csv_info.total_records for csv_info in csv_records)
    total_batches = sum(csv_info.total_batches for csv_info in csv_records)
    
    # Start processing stage with CSV count
    csv_stage.start_processing(len(csv_records))
    
    # Update processing with total records
    csv_stage.update_processing(
        completed_files=0,
        total_records=total_records
    )
    
    logger.info(f"Total records: {total_records}")
    logger.info(f"Total batches: {total_batches}")