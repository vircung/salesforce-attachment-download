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
            - chunk_size: int (for file download chunk size)
            - log_file: Path (log file path)
            - use_csv_mode: bool (always True - only CSV workflow supported)
            - records_dir_resolved: Optional[Path] (resolved records directory)
    """
    # Load environment variables from .env file (if present)
    load_dotenv()

    # Get environment variables with defaults
    env_org_alias = os.getenv('SF_ORG_ALIAS')
    env_output_dir = os.getenv('OUTPUT_DIR', './output')
    env_log_file = os.getenv('LOG_FILE', './logs/download.log')
    env_chunk_size = os.getenv('CHUNK_SIZE', '8192')

    # CSV Records processing configuration from .env
    env_records_dir = os.getenv('RECORDS_DIR')
    env_batch_size = os.getenv('BATCH_SIZE', '100')

    # Validate and convert CHUNK_SIZE to int
    try:
        chunk_size = int(env_chunk_size)
    except ValueError:
        logger.warning(f"Invalid CHUNK_SIZE value '{env_chunk_size}', using default 8192")
        chunk_size = 8192

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
        '--records-dir',
        type=Path,
        default=None,
        required=True,
        help='Directory containing CSV files with record IDs (column: Id). Required for CSV-based processing.'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=default_batch_size,
        help=f'Number of ParentIds per SOQL query batch (default: {default_batch_size})'
    )

    args = parser.parse_args()

    # Add additional configuration to args
    args.chunk_size = chunk_size
    args.log_file = Path(env_log_file)

    # CSV mode is always enabled (only workflow supported)
    # Resolve records directory from CLI or env
    if args.records_dir:
        records_dir_resolved = args.records_dir
    elif env_records_dir:
        records_dir_resolved = Path(env_records_dir)
    else:
        records_dir_resolved = None

    args.use_csv_mode = True
    args.records_dir_resolved = records_dir_resolved

    return args
