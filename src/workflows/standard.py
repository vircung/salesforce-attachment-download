"""
Standard Workflow Module

High-level workflow for standard attachment extraction
(query + download).
"""

import sys
import logging
from pathlib import Path
from typing import Dict
from argparse import Namespace

from src.query.executor import run_query_script
from src.query.pagination import run_paginated_query
from src.query.filters import parse_filter_config
from src.csv.validator import validate_metadata_csv
from src.download.downloader import download_attachments

logger = logging.getLogger(__name__)


def process_standard_workflow(args: Namespace, chunk_size: int = 8192) -> Dict:
    """
    Execute standard attachment extraction workflow.

    Workflow:
    1. Parse filter configuration (if any)
    2. Query attachments (single query or paginated) OR use provided CSV
    3. Download attachment files

    Args:
        args: Parsed command-line arguments from argparse
        chunk_size: Download chunk size in bytes (default: 8192)

    Returns:
        Dictionary with download statistics:
        {
            'total': int,
            'success': int,
            'failed': int,
            'skipped': int
        }

    Raises:
        RuntimeError: If query or download fails
        ValueError: If metadata CSV validation fails
    """
    # Parse filter configuration
    filter_config = parse_filter_config(
        prefix_str=args.parent_id_prefix,
        ids_str=args.parent_ids,
        strategy=args.filter_strategy
    )

    if filter_config:
        logger.info(f"Filter configuration: {filter_config}")
    else:
        logger.info("No filtering configured - will download all attachments")

    # Step 1: Query attachments (or use provided CSV)
    if args.metadata:
        # User provided existing CSV - validate and use it
        logger.info("=" * 70)
        logger.info("USING PROVIDED METADATA CSV")
        logger.info("=" * 70)
        logger.info(f"CSV file: {args.metadata}")

        # Validate CSV structure
        is_valid, error_msg = validate_metadata_csv(args.metadata)
        if not is_valid:
            logger.error("=" * 70)
            logger.error("CSV VALIDATION FAILED")
            logger.error("=" * 70)
            logger.error(f"Error: {error_msg}")
            logger.error("")
            logger.error("Please ensure your CSV file:")
            logger.error("  1. Exists and is readable")
            logger.error("  2. Has a header row with column names")
            logger.error("  3. Contains required columns: 'Id' and 'Name'")
            logger.error("  4. Contains recommended column: 'ParentId' (needed for filtering)")
            logger.error("  5. Has at least one data row")
            logger.error("  6. Is UTF-8 encoded")
            logger.error("")
            logger.error("You can generate a valid CSV by querying Salesforce:")
            logger.error(f"  python {sys.argv[0]} --org your-org --query-limit 100")
            sys.exit(1)

        csv_path = args.metadata
        logger.info("✓ CSV validation passed")
        logger.info(f"✓ Ready to download attachments from metadata")
    else:
        # No CSV provided - query from Salesforce
        metadata_dir = args.output / 'metadata'

        # Check if pagination is configured
        if args.target_count and args.target_count > 0:
            logger.info(f"Pagination enabled: target={args.target_count}, mode={args.target_mode}")
            csv_path = run_paginated_query(
                org_alias=args.org,
                output_dir=metadata_dir,
                target_count=args.target_count,
                batch_size=args.query_limit,
                target_mode=args.target_mode,
                filter_config=filter_config
            )
        else:
            # Legacy single query mode
            logger.info("Single query mode (pagination disabled)")
            csv_path = run_query_script(args.org, metadata_dir, args.query_limit)

        logger.info(f"Generated metadata: {csv_path}")

    # Step 2: Download files
    files_dir = args.output / 'files'

    # If pagination was used with Python filters, filters were already applied
    # Don't apply them again in the downloader
    downloader_filter_config = filter_config
    if args.target_count and args.target_count > 0:
        if filter_config and filter_config.strategy == 'python':
            logger.info("Python filters already applied during pagination - skipping filter in downloader")
            downloader_filter_config = None

    stats = download_attachments(
        metadata_csv=csv_path,
        output_dir=files_dir,
        org_alias=args.org,
        chunk_size=chunk_size,
        filter_config=downloader_filter_config
    )

    # Final summary
    logger.info("=" * 70)
    logger.info("WORKFLOW COMPLETE")
    logger.info("=" * 70)
    logger.info(f"Metadata: {csv_path}")
    logger.info(f"Files: {files_dir}")
    logger.info(f"Success: {stats['success']}/{stats['total']}")

    return stats
