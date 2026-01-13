"""
Common Workflow Utilities

Shared helper functions for workflow modules to reduce code duplication
and ensure consistent logging, directory management, and data processing.
"""

import csv
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from src.utils import log_section_header

logger = logging.getLogger(__name__)


def ensure_directories(*dirs: Path) -> None:
    """
    Create multiple directories if they don't exist.
    
    Creates directories with parent directories as needed, similar to
    'mkdir -p'. Silently succeeds if directories already exist.
    
    Args:
        *dirs: Variable number of Path objects to create
    
    Example:
        >>> ensure_directories(Path('./output/metadata'), Path('./output/files'))
        # Creates both directories and any missing parent directories
    
    Raises:
        OSError: If directory creation fails due to permissions or other I/O errors
    """
    for directory in dirs:
        directory.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Directory ensured: {directory}")


def merge_csv_files(
    csv_paths: List[Path], 
    output_path: Path
) -> int:
    """
    Merge multiple CSV files into a single file.
    
    Reads multiple CSV files with the same column structure and combines
    them into a single output file. All files must have identical column
    headers. The header is written once, followed by all data rows.
    
    Args:
        csv_paths: List of CSV file paths to merge (must have same columns)
        output_path: Path for the merged output CSV file
        
    Returns:
        Total number of data rows merged (excluding header)
        
    Raises:
        ValueError: If CSV files have different columns or if no files provided
        FileNotFoundError: If any input CSV file doesn't exist
    
    Example:
        >>> paths = [Path('batch1.csv'), Path('batch2.csv')]
        >>> count = merge_csv_files(paths, Path('merged.csv'))
        >>> print(f"Merged {count} rows")
    """
    if not csv_paths:
        raise ValueError("No CSV files provided for merging")
    
    logger.info(f"Merging {len(csv_paths)} CSV file(s) into: {output_path.name}")
    
    accumulated_rows = []
    fieldnames = None
    
    # Read all CSV files and accumulate rows
    for csv_path in csv_paths:
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")
        
        with csv_path.open('r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            # Capture fieldnames from first file
            if fieldnames is None:
                fieldnames = reader.fieldnames
                logger.debug(f"CSV columns: {fieldnames}")
            else:
                # Validate that all files have same columns
                if reader.fieldnames != fieldnames:
                    raise ValueError(
                        f"Column mismatch in {csv_path.name}. "
                        f"Expected: {fieldnames}, Got: {reader.fieldnames}"
                    )
            
            # Accumulate all rows
            batch_rows = list(reader)
            accumulated_rows.extend(batch_rows)
            logger.debug(f"Read {len(batch_rows)} rows from {csv_path.name}")
    
    # Write merged CSV
    with output_path.open('w', encoding='utf-8', newline='') as f:
        if fieldnames:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(accumulated_rows)
        else:
            logger.warning("No fieldnames captured - writing empty CSV")
    
    logger.info(f"Merged CSV created with {len(accumulated_rows)} row(s)")
    return len(accumulated_rows)


def log_download_summary(
    stats: Dict[str, Any],
    metadata_path: Optional[Path] = None,
    files_dir: Optional[Path] = None
) -> None:
    """
    Log standardized download summary with statistics.
    
    Creates a formatted summary section showing download results with
    counts for total, successful, skipped, and failed downloads.
    Optionally includes metadata source and output directory paths.
    
    Args:
        stats: Dictionary with download statistics, must include keys:
               - 'total': Total number of attachments
               - 'success': Number of successful downloads
               - 'failed': Number of failed downloads
               - 'skipped': Number of files skipped (optional, default: 0)
        metadata_path: Optional path to metadata CSV file
        files_dir: Optional path to downloaded files directory
    
    Example:
        >>> stats = {'total': 100, 'success': 95, 'failed': 5, 'skipped': 10}
        >>> log_download_summary(stats, Path('metadata.csv'), Path('./files'))
        # Logs:
        # ======================================================================
        # WORKFLOW COMPLETE
        # ======================================================================
        # Metadata: metadata.csv
        # Files: ./files
        # Downloaded: 95/100
        # Skipped (already exists): 10
    """
    log_section_header("WORKFLOW COMPLETE")
    
    if metadata_path:
        logger.info(f"Metadata: {metadata_path}")
    if files_dir:
        logger.info(f"Files: {files_dir}")
    
    logger.info(f"Downloaded: {stats['success']}/{stats['total']}")
    
    if stats.get('skipped', 0) > 0:
        logger.info(f"Skipped (already exists): {stats['skipped']}")
    
    if stats.get('failed', 0) > 0:
        logger.info(f"Failed: {stats['failed']}")
