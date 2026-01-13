"""
CSV Records Workflow Module

High-level workflow for processing CSV files containing record IDs
and downloading their associated attachments.
"""

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict

from src.query.executor import run_query_script_with_filter
from src.query.filters import ParentIdFilter, build_soql_where_clause
from src.csv.processor import process_records_directory
from src.download.downloader import download_attachments

logger = logging.getLogger(__name__)


def process_csv_records_workflow(
    org_alias: str,
    output_dir: Path,
    records_dir: Path,
    batch_size: int = 100,
    download: bool = True
) -> Dict[str, any]:
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
    """
    logger.info("=" * 70)
    logger.info("CSV-BASED ATTACHMENT EXTRACTION WORKFLOW")
    logger.info("=" * 70)
    logger.info(f"Org: {org_alias}")
    logger.info(f"Records directory: {records_dir.absolute()}")
    logger.info(f"Output directory: {output_dir.absolute()}")
    logger.info(f"Batch size: {batch_size}")
    logger.info(f"Download enabled: {download}")
    logger.info("")

    # Process CSV files - validates, extracts IDs, creates batches
    csv_records = process_records_directory(records_dir, batch_size)

    # Statistics tracking
    stats = {
        'total_csv_files': len(csv_records),
        'total_records': 0,
        'total_batches': 0,
        'total_attachments': 0,
        'per_csv': []
    }

    failed_files = []

    # Process each CSV file
    for csv_idx, csv_info in enumerate(csv_records, start=1):
        logger.info("=" * 70)
        logger.info(f"PROCESSING CSV {csv_idx}/{len(csv_records)}: {csv_info.csv_name}.csv")
        logger.info("=" * 70)
        logger.info(f"Records: {csv_info.total_records}")
        logger.info(f"Batches: {csv_info.total_batches}")
        logger.info("")

        try:
            # Create output subdirectories for this CSV
            csv_output_dir = output_dir / csv_info.csv_name
            csv_metadata_dir = csv_output_dir / 'metadata'
            csv_files_dir = csv_output_dir / 'files'

            csv_metadata_dir.mkdir(parents=True, exist_ok=True)
            csv_files_dir.mkdir(parents=True, exist_ok=True)

            logger.info(f"Output directories:")
            logger.info(f"  Metadata: {csv_metadata_dir}")
            logger.info(f"  Files: {csv_files_dir}")
            logger.info("")

            # Query attachments for each batch
            batch_csv_paths = []
            accumulated_attachments = []
            csv_fieldnames = None

            for batch_idx, id_batch in enumerate(csv_info.id_batches):
                logger.info(f"Batch {batch_idx + 1}/{csv_info.total_batches}: Querying {len(id_batch)} ParentId(s)")

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

                # Read batch results
                with batch_csv_path.open('r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)

                    # Capture fieldnames from first batch
                    if csv_fieldnames is None:
                        csv_fieldnames = reader.fieldnames
                        logger.debug(f"Captured fieldnames: {csv_fieldnames}")

                    # Accumulate all attachments
                    batch_attachments = list(reader)
                    accumulated_attachments.extend(batch_attachments)

                    logger.info(f"Batch {batch_idx + 1}/{csv_info.total_batches}: Found {len(batch_attachments)} attachment(s)")

                logger.info("")

            # Merge all batch results into single CSV
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            merged_csv_path = csv_metadata_dir / f"attachments_{timestamp}_merged.csv"

            logger.info(f"Merging {len(batch_csv_paths)} batch CSV(s) into: {merged_csv_path.name}")

            with merged_csv_path.open('w', encoding='utf-8', newline='') as f:
                if csv_fieldnames:
                    writer = csv.DictWriter(f, fieldnames=csv_fieldnames)
                    writer.writeheader()
                    writer.writerows(accumulated_attachments)
                else:
                    logger.warning("No fieldnames captured - writing empty CSV")

            logger.info(f"Merged CSV created with {len(accumulated_attachments)} attachment(s)")
            logger.info("")

            # Download attachments if enabled
            downloaded_count = 0
            if download and len(accumulated_attachments) > 0:
                logger.info(f"Downloading {len(accumulated_attachments)} attachment(s) to: {csv_files_dir}")
                logger.info("")

                try:
                    downloaded_count = download_attachments(
                        org_alias=org_alias,
                        metadata_csv=merged_csv_path,
                        output_dir=csv_files_dir,
                        filter_config=None  # No additional filtering needed
                    )
                    logger.info(f"Downloaded {downloaded_count}/{len(accumulated_attachments)} file(s)")
                except Exception as e:
                    logger.error(f"Download failed for {csv_info.csv_name}: {e}")
                    # Continue processing other CSVs even if download fails
            elif download and len(accumulated_attachments) == 0:
                logger.info("No attachments to download")
            else:
                logger.info("Download skipped (download=False)")

            # Record statistics for this CSV
            csv_stats = {
                'csv_name': csv_info.csv_name,
                'records': csv_info.total_records,
                'batches': csv_info.total_batches,
                'attachments': len(accumulated_attachments),
                'downloaded': downloaded_count,
                'output_dir': str(csv_output_dir)
            }
            stats['per_csv'].append(csv_stats)
            stats['total_records'] += csv_info.total_records
            stats['total_batches'] += csv_info.total_batches
            stats['total_attachments'] += len(accumulated_attachments)

            logger.info(f"✓ Completed {csv_info.csv_name}.csv")
            logger.info("")

        except Exception as e:
            logger.error(f"✗ Failed to process {csv_info.csv_name}.csv: {e}")
            failed_files.append(csv_info.csv_name)
            logger.info("")
            # Continue processing other CSV files

    # Final summary
    logger.info("=" * 70)
    logger.info("WORKFLOW SUMMARY")
    logger.info("=" * 70)
    logger.info(f"Total CSV files: {stats['total_csv_files']}")
    logger.info(f"Total records: {stats['total_records']}")
    logger.info(f"Total batches executed: {stats['total_batches']}")
    logger.info(f"Total attachments found: {stats['total_attachments']}")

    if failed_files:
        logger.warning(f"Failed to process {len(failed_files)} file(s): {', '.join(failed_files)}")
    else:
        logger.info("All CSV files processed successfully!")

    logger.info("")

    return stats
