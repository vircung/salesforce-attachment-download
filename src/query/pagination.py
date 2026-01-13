"""
Pagination Module

Handles paginated SOQL queries with OFFSET support.
"""

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

from src.query.executor import run_query_script
from src.query.filters import ParentIdFilter, apply_parent_id_filter

logger = logging.getLogger(__name__)


def run_paginated_query(
    org_alias: str,
    output_dir: Path,
    target_count: int,
    batch_size: int,
    target_mode: str = 'exact',
    filter_config: Optional[ParentIdFilter] = None
) -> Path:
    """
    Run paginated queries to fetch target number of attachment records.

    Uses SOQL OFFSET to paginate through results. For Python filter strategy,
    continues fetching until enough filtered matches are found.

    Args:
        org_alias: Salesforce org alias
        output_dir: Directory to save merged metadata CSV
        target_count: Target number of records to fetch
        batch_size: Number of records per query (QUERY_LIMIT)
        target_mode: 'exact' (trim to target) or 'minimum' (at least target)
        filter_config: Optional filter configuration for ParentId filtering

    Returns:
        Path to the merged CSV file with all paginated records

    Raises:
        RuntimeError: If queries fail or OFFSET limit exceeded
        ValueError: If parameters are invalid
    """
    if target_count <= 0:
        raise ValueError(f"TARGET_COUNT must be positive, got {target_count}")

    if batch_size <= 0:
        raise ValueError(f"QUERY_LIMIT must be positive, got {batch_size}")

    # SOQL OFFSET limit
    MAX_OFFSET = 2000

    logger.info("=" * 70)
    logger.info("PAGINATION MODE ENABLED")
    logger.info("=" * 70)
    logger.info(f"Target count: {target_count}")
    logger.info(f"Batch size: {batch_size}")
    logger.info(f"Target mode: {target_mode}")

    if filter_config and filter_config.has_filters():
        logger.info(f"Filter config: {filter_config}")

    # Create metadata directory
    output_dir.mkdir(parents=True, exist_ok=True)

    accumulated_records: List[Dict[str, str]] = []
    offset = 0
    batch_num = 1
    csv_fieldnames: Optional[List[str]] = None

    # Determine if we need to apply Python filtering
    needs_python_filter = (
        filter_config and
        filter_config.has_filters() and
        filter_config.strategy == 'python'
    )

    while True:
        # Check OFFSET limit
        if offset > MAX_OFFSET:
            logger.error(
                f"SOQL OFFSET limit exceeded ({MAX_OFFSET}). "
                f"Cannot fetch more records. Consider reducing TARGET_COUNT."
            )
            raise RuntimeError(f"OFFSET limit {MAX_OFFSET} exceeded")

        # Optimize: if target already reached and not using Python filters, stop
        if not needs_python_filter and len(accumulated_records) >= target_count:
            logger.info(f"Target count {target_count} reached. Stopping pagination.")
            break

        # For Python filters, check filtered count
        if needs_python_filter:
            filtered_count = len(accumulated_records)
            if filtered_count >= target_count:
                logger.info(
                    f"Filtered target count {target_count} reached "
                    f"({filtered_count} filtered records). Stopping pagination."
                )
                break

        logger.info(f"Fetching batch {batch_num} (OFFSET {offset}, LIMIT {batch_size})...")

        try:
            # Execute query for this batch
            batch_csv_path = run_query_script(
                org_alias=org_alias,
                output_dir=output_dir,
                query_limit=batch_size,
                offset=offset
            )

            # Read batch records
            batch_records = []
            with batch_csv_path.open('r', encoding='utf-8') as f:
                reader = csv.DictReader(f)

                # Capture fieldnames from first batch
                if csv_fieldnames is None:
                    csv_fieldnames = reader.fieldnames

                for row in reader:
                    batch_records.append(row)

            logger.info(f"Batch {batch_num}: Retrieved {len(batch_records)} records")

            # If empty batch, no more records available
            if len(batch_records) == 0:
                logger.info("Empty batch received. No more records available.")
                break

            # Apply Python filter if configured
            if needs_python_filter:
                original_count = len(batch_records)
                batch_records = apply_parent_id_filter(batch_records, filter_config)
                filtered_count = len(batch_records)
                logger.info(
                    f"Batch {batch_num}: Filtered {original_count} → {filtered_count} records"
                )

            # Accumulate records
            accumulated_records.extend(batch_records)

            # Update counters
            offset += batch_size
            batch_num += 1

            # For exact mode without filters: trim if we exceeded target
            if not needs_python_filter and target_mode == 'exact':
                if len(accumulated_records) >= target_count:
                    break

            # For minimum mode: stop when we have at least target count
            if target_mode == 'minimum' and len(accumulated_records) >= target_count:
                logger.info(
                    f"Minimum target {target_count} reached "
                    f"(have {len(accumulated_records)} records). Stopping pagination."
                )
                break

        except Exception as e:
            logger.error(f"Error during pagination at batch {batch_num}: {e}")
            raise

    # Apply target mode trimming for 'exact' mode
    total_fetched = len(accumulated_records)

    if target_mode == 'exact' and total_fetched > target_count:
        logger.info(f"Trimming {total_fetched} records to exactly {target_count}")
        accumulated_records = accumulated_records[:target_count]

    final_count = len(accumulated_records)

    logger.info("=" * 70)
    logger.info("PAGINATION SUMMARY")
    logger.info("=" * 70)
    logger.info(f"Total batches fetched: {batch_num - 1}")
    logger.info(f"Target count: {target_count}")
    logger.info(f"Final record count: {final_count}")

    if final_count < target_count:
        logger.warning(
            f"Fetched only {final_count} records (target was {target_count}). "
            f"All available records have been retrieved."
        )

    # Write merged CSV
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    merged_csv_path = output_dir / f"attachments_{timestamp}_paginated.csv"

    logger.info(f"Writing merged CSV: {merged_csv_path}")

    with merged_csv_path.open('w', encoding='utf-8', newline='') as f:
        if csv_fieldnames:
            writer = csv.DictWriter(f, fieldnames=csv_fieldnames)
            writer.writeheader()
            writer.writerows(accumulated_records)
        else:
            logger.warning("No fieldnames captured, empty CSV written")

    logger.info(f"Merged CSV created with {final_count} records")

    return merged_csv_path
