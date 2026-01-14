"""
CLI Configuration Module

Handles command-line argument parsing and environment configuration.
"""

import os
import argparse
import logging
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


def parse_arguments():
    """
    Parse command-line arguments and load environment configuration.

    Returns:
        argparse.Namespace: Parsed arguments with additional attributes:
            - chunk_size: int
            - log_file: Path
            - use_csv_mode: bool
            - records_dir_resolved: Optional[Path]
    """
    # Load environment variables from .env file (if present)
    load_dotenv()

    # Get environment variables with defaults
    env_org_alias = os.getenv('SF_ORG_ALIAS')
    env_output_dir = os.getenv('OUTPUT_DIR', './output')
    env_log_file = os.getenv('LOG_FILE', './logs/download.log')
    env_chunk_size = os.getenv('CHUNK_SIZE', '8192')
    env_metadata_csv = os.getenv('METADATA_CSV')

    # Filter configuration from .env
    env_parent_id_prefix = os.getenv('PARENT_ID_PREFIX')
    env_parent_ids = os.getenv('PARENT_IDS')
    env_filter_strategy = os.getenv('FILTER_STRATEGY', 'python')

    # Query limit from .env
    env_query_limit = os.getenv('QUERY_LIMIT', '100')

    # Pagination configuration from .env
    env_target_count = os.getenv('TARGET_COUNT', '')
    env_target_mode = os.getenv('TARGET_MODE', 'exact')

    # CSV Records processing configuration from .env
    env_records_dir = os.getenv('RECORDS_DIR')
    env_batch_size = os.getenv('BATCH_SIZE', '100')

    # Validate and convert CHUNK_SIZE to int
    try:
        chunk_size = int(env_chunk_size)
    except ValueError:
        logger.warning(f"Invalid CHUNK_SIZE value '{env_chunk_size}', using default 8192")
        chunk_size = 8192

    # Validate and convert QUERY_LIMIT to int
    try:
        default_query_limit = int(env_query_limit)
    except ValueError:
        logger.warning(f"Invalid QUERY_LIMIT value '{env_query_limit}', using default 100")
        default_query_limit = 100

    # Validate and convert TARGET_COUNT to int (optional)
    default_target_count = None
    if env_target_count and env_target_count.strip():
        try:
            default_target_count = int(env_target_count)
            if default_target_count <= 0:
                logger.warning(f"TARGET_COUNT must be positive, got {default_target_count}. Pagination disabled.")
                default_target_count = None
        except ValueError:
            logger.warning(f"Invalid TARGET_COUNT value '{env_target_count}', pagination disabled")
            default_target_count = None

    # Validate TARGET_MODE
    if env_target_mode not in ['exact', 'minimum']:
        logger.warning(f"Invalid TARGET_MODE value '{env_target_mode}', using default 'exact'")
        env_target_mode = 'exact'

    # Validate and convert BATCH_SIZE to int
    default_batch_size = 100
    try:
        default_batch_size = int(env_batch_size)
        if default_batch_size < 1:
            logger.warning(f"BATCH_SIZE must be at least 1, got {default_batch_size}. Using default 100.")
            default_batch_size = 100
    except ValueError:
        logger.warning(f"Invalid BATCH_SIZE value '{env_batch_size}', using default 100")
        default_batch_size = 100

    parser = argparse.ArgumentParser(
        description='Query and download Salesforce attachments'
    )
    parser.add_argument(
        '--org',
        type=str,
        default=env_org_alias,
        help=f'Salesforce org alias (default: {env_org_alias or "use default org"})'
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=Path(env_output_dir),
        help=f'Base output directory (default: {env_output_dir})'
    )
    parser.add_argument(
        '--skip-query',
        action='store_true',
        help='(Deprecated) Skip query step - use --metadata instead'
    )
    parser.add_argument(
        '--metadata',
        type=lambda p: Path(p) if p else None,
        default=Path(env_metadata_csv) if env_metadata_csv and env_metadata_csv.strip() else None,
        help='Path to existing metadata CSV (skips Salesforce query)'
    )
    parser.add_argument(
        '--parent-id-prefix',
        type=str,
        default=env_parent_id_prefix,
        help='Comma-separated ParentId prefixes to filter (e.g., "aBo,001")'
    )
    parser.add_argument(
        '--parent-ids',
        type=str,
        default=env_parent_ids,
        help='Comma-separated specific ParentIds to filter'
    )
    parser.add_argument(
        '--filter-strategy',
        type=str,
        choices=['python', 'soql'],
        default=env_filter_strategy,
        help='Filtering strategy: python (post-query) or soql (in-query)'
    )
    parser.add_argument(
        '--query-limit',
        type=int,
        default=default_query_limit,
        help=f'Maximum number of records to query per batch (default: {default_query_limit})'
    )
    parser.add_argument(
        '--target-count',
        type=int,
        default=default_target_count,
        help='Target number of attachments to retrieve using pagination (optional)'
    )
    parser.add_argument(
        '--target-mode',
        type=str,
        choices=['exact', 'minimum'],
        default=env_target_mode,
        help='Target mode: exact (trim to TARGET_COUNT) or minimum (at least TARGET_COUNT)'
    )
    parser.add_argument(
        '--records-dir',
        type=Path,
        default=None,
        help='Directory containing CSV files with record IDs (column: Id). Enables CSV-based processing mode.'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=default_batch_size,
        help=f'Number of ParentIds per SOQL query batch for CSV mode (default: {default_batch_size})'
    )

    args = parser.parse_args()

    # Add additional configuration to args
    args.chunk_size = chunk_size
    args.log_file = Path(env_log_file)

    # Automatic mode detection for CSV-records workflow
    use_csv_mode = False
    records_dir_resolved = None

    if args.records_dir:
        # CLI argument takes precedence
        records_dir_resolved = args.records_dir
        use_csv_mode = True
        logger.info(f"CSV-records mode activated via --records-dir: {records_dir_resolved}")
    elif env_records_dir:
        # Check if .env RECORDS_DIR exists
        records_dir_resolved = Path(env_records_dir)
        if records_dir_resolved.exists() and records_dir_resolved.is_dir():
            use_csv_mode = True
            logger.info(f"CSV-records mode activated via RECORDS_DIR env: {records_dir_resolved}")
        else:
            logger.debug(f"RECORDS_DIR set but directory not found: {records_dir_resolved}")

    args.use_csv_mode = use_csv_mode
    args.records_dir_resolved = records_dir_resolved

    return args
