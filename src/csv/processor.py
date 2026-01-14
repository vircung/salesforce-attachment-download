"""
CSV Records Processor Module

Handles CSV file discovery, validation, ID extraction, and batching
for CSV-based attachment extraction workflow.
"""

import csv
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


@dataclass
class CsvRecordInfo:
    """
    Information about a CSV file and its records.

    Attributes:
        csv_path: Path to the CSV file
        csv_name: Filename without extension (used for output directory)
        record_ids: List of extracted record IDs
        total_records: Total number of valid record IDs found
        id_batches: List of ID batches (each batch contains up to batch_size IDs)
        total_batches: Number of batches created
    """
    csv_path: Path
    csv_name: str
    record_ids: List[str]
    total_records: int
    id_batches: List[List[str]]
    total_batches: int

    def __str__(self) -> str:
        """String representation for logging."""
        return (
            f"CsvRecordInfo(csv_name='{self.csv_name}', "
            f"total_records={self.total_records}, "
            f"total_batches={self.total_batches})"
        )


def discover_csv_files(records_dir: Path) -> List[Path]:
    """
    Discover all CSV files in the specified directory.

    Args:
        records_dir: Directory to search for CSV files

    Returns:
        Sorted list of CSV file paths (by filename)

    Raises:
        FileNotFoundError: If directory doesn't exist
        ValueError: If directory exists but contains no CSV files
    """
    if not records_dir.exists():
        raise FileNotFoundError(
            f"Records directory not found: {records_dir.absolute()}"
        )

    if not records_dir.is_dir():
        raise ValueError(
            f"Path is not a directory: {records_dir.absolute()}"
        )

    # Find all CSV files
    csv_files = sorted(records_dir.glob("*.csv"))

    if not csv_files:
        raise ValueError(
            f"No CSV files found in directory: {records_dir.absolute()}"
        )

    logger.info(f"Discovered {len(csv_files)} CSV file(s) in {records_dir.name}")
    for csv_file in csv_files:
        logger.debug(f"  - {csv_file.name}")

    return csv_files


def validate_csv_structure(csv_path: Path) -> bool:
    """
    Validate that CSV file has required 'Id' column.

    Args:
        csv_path: Path to CSV file to validate

    Returns:
        True if valid

    Raises:
        FileNotFoundError: If CSV file doesn't exist
        ValueError: If CSV file is missing 'Id' column or is empty
    """
    if not csv_path.exists():
        raise FileNotFoundError(
            f"CSV file not found: {csv_path.absolute()}"
        )

    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            # Check for Id column
            if reader.fieldnames is None:
                raise ValueError(
                    f"CSV file '{csv_path.name}' is empty or has no header"
                )

            if 'Id' not in reader.fieldnames:
                raise ValueError(
                    f"CSV file '{csv_path.name}' is missing required column 'Id'. "
                    f"Found columns: {', '.join(reader.fieldnames)}"
                )

            logger.debug(f"CSV file '{csv_path.name}' validated successfully")
            return True

    except csv.Error as e:
        raise ValueError(
            f"Failed to read CSV file '{csv_path.name}': {e}"
        )


def extract_ids_from_csv(csv_path: Path) -> List[str]:
    """
    Extract unique record IDs from CSV file.

    Reads the 'Id' column from CSV and returns unique non-empty values,
    preserving order of first occurrence.

    Args:
        csv_path: Path to CSV file

    Returns:
        List of unique record IDs (preserves order)

    Raises:
        FileNotFoundError: If CSV file doesn't exist
        ValueError: If CSV structure is invalid
    """
    # Validate structure first
    validate_csv_structure(csv_path)

    record_ids = []
    seen_ids = set()
    skipped_count = 0

    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
                record_id = row.get('Id', '').strip()

                # Skip empty IDs
                if not record_id:
                    skipped_count += 1
                    logger.debug(f"Row {row_num}: Skipping empty Id")
                    continue

                # Skip duplicate IDs
                if record_id in seen_ids:
                    logger.debug(f"Row {row_num}: Skipping duplicate Id '{record_id}'")
                    continue

                # Add unique ID
                record_ids.append(record_id)
                seen_ids.add(record_id)

        logger.debug(
            f"Extracted {len(record_ids)} unique ID(s) from '{csv_path.name}'"
        )

        if skipped_count > 0:
            logger.debug(
                f"Skipped {skipped_count} row(s) with empty or duplicate IDs"
            )

        if not record_ids:
            logger.warning(
                f"No valid IDs found in '{csv_path.name}'. "
                f"Check that the 'Id' column contains non-empty values."
            )

        return record_ids

    except csv.Error as e:
        raise ValueError(
            f"Failed to extract IDs from '{csv_path.name}': {e}"
        )


def batch_ids(ids: List[str], batch_size: int) -> List[List[str]]:
    """
    Split list of IDs into batches of specified size.

    Args:
        ids: List of record IDs to batch
        batch_size: Maximum number of IDs per batch

    Returns:
        List of batches, where each batch is a list of IDs

    Raises:
        ValueError: If batch_size is less than 1

    Example:
        >>> ids = ['id1', 'id2', 'id3', 'id4', 'id5']
        >>> batches = batch_ids(ids, batch_size=2)
        >>> print(batches)
        [['id1', 'id2'], ['id3', 'id4'], ['id5']]
    """
    if batch_size < 1:
        raise ValueError(f"batch_size must be at least 1, got {batch_size}")

    if not ids:
        logger.warning("batch_ids called with empty ID list")
        return []

    batches = []
    for i in range(0, len(ids), batch_size):
        batch = ids[i:i + batch_size]
        batches.append(batch)

    logger.debug(
        f"Split {len(ids)} ID(s) into {len(batches)} batch(es) "
        f"of size {batch_size}"
    )

    return batches


def prepare_csv_record_info(
    csv_path: Path,
    batch_size: int = 100
) -> CsvRecordInfo:
    """
    Prepare complete CSV record information including batching.

    This is a convenience function that combines validation, ID extraction,
    and batching into a single call.

    Args:
        csv_path: Path to CSV file
        batch_size: Maximum number of IDs per batch (default: 100)

    Returns:
        CsvRecordInfo with all processing metadata

    Raises:
        FileNotFoundError: If CSV file doesn't exist
        ValueError: If CSV structure is invalid or batch_size < 1
    """
    logger.debug(f"Processing CSV file: {csv_path.name}")

    # Extract IDs
    record_ids = extract_ids_from_csv(csv_path)

    # Create batches
    id_batches = batch_ids(record_ids, batch_size)

    # Prepare info object
    csv_name = csv_path.stem  # Filename without extension
    info = CsvRecordInfo(
        csv_path=csv_path,
        csv_name=csv_name,
        record_ids=record_ids,
        total_records=len(record_ids),
        id_batches=id_batches,
        total_batches=len(id_batches)
    )

    logger.debug(
        f"Prepared: {info.total_records} record(s) in {info.total_batches} batch(es)"
    )

    return info


def process_records_directory(
    records_dir: Path,
    batch_size: int = 100
) -> List[CsvRecordInfo]:
    """
    Process all CSV files in directory and prepare for querying.

    Discovers, validates, and prepares all CSV files in the directory.

    Args:
        records_dir: Directory containing CSV files
        batch_size: Maximum number of IDs per batch (default: 100)

    Returns:
        List of CsvRecordInfo objects (one per CSV file)

    Raises:
        FileNotFoundError: If directory doesn't exist
        ValueError: If no CSV files found or any CSV is invalid
    """
    logger.debug("=" * 60)
    logger.debug("CSV RECORDS PROCESSING")
    logger.debug("=" * 60)
    logger.debug(f"Records directory: {records_dir.absolute()}")
    logger.debug(f"Batch size: {batch_size}")

    # Discover CSV files
    csv_files = discover_csv_files(records_dir)

    # Process each CSV
    csv_records = []
    for csv_path in csv_files:
        try:
            info = prepare_csv_record_info(csv_path, batch_size)
            csv_records.append(info)
        except ValueError as e:
            logger.error(f"Failed to process '{csv_path.name}': {e}")
            raise

    # Log summary (keep INFO for user visibility)
    total_records = sum(info.total_records for info in csv_records)
    total_batches = sum(info.total_batches for info in csv_records)

    logger.info(f"Found {len(csv_records)} CSV file(s): {total_records} records in {total_batches} batch(es)")

    return csv_records
