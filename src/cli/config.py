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
            - log_file: Path (log file path)
            - records_dir_resolved: Optional[Path] (resolved records directory)
    """
    # Load environment variables from .env file (if present)
    load_dotenv()

    # Get environment variables with defaults
    env_org_alias = os.getenv('SF_ORG_ALIAS')
    env_output_dir = os.getenv('OUTPUT_DIR', './output')
    env_log_file = os.getenv('LOG_FILE', './logs/download.log')

    # CSV Records processing configuration from .env
    env_records_dir = os.getenv('RECORDS_DIR')
    env_batch_size = os.getenv('BATCH_SIZE', '100')
    env_download_workers = os.getenv('DOWNLOAD_WORKERS', '1')
    
    # Logging configuration from .env
    env_verbose = os.getenv('VERBOSE', 'false').lower() in ('true', '1', 'yes')
    env_debug = os.getenv('DEBUG', 'false').lower() in ('true', '1', 'yes')

    # Progress display configuration from .env
    env_progress = os.getenv('PROGRESS', 'auto').lower()
    if env_progress not in ('auto', 'on', 'off'):
        logger.warning(f"Invalid PROGRESS value '{env_progress}', using default 'auto'")
        env_progress = 'auto'


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

    # Validate and convert DOWNLOAD_WORKERS to int
    default_download_workers = 1
    try:
        default_download_workers = int(env_download_workers)
        if default_download_workers < 1:
            logger.warning(
                f"DOWNLOAD_WORKERS must be at least 1, got {default_download_workers}. Using default 1."
            )
            default_download_workers = 1
    except ValueError:
        logger.warning(
            f"Invalid DOWNLOAD_WORKERS value '{env_download_workers}', using default 1"
        )
        default_download_workers = 1


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
        default=Path(env_records_dir) if env_records_dir else None,
        help=f'Directory containing CSV files with record IDs (column: Id). Required for CSV-based processing. (default: {env_records_dir or "not set"})'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=default_batch_size,
        help=f'Number of ParentIds per SOQL query batch (default: {default_batch_size})'
    )
    parser.add_argument(
        '--download-workers',
        type=int,
        default=default_download_workers,
        help=f'Parallel downloads per bucket (default: {default_download_workers})'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        default=env_verbose,
        help='Alias for default behavior (INFO level). Kept for compatibility.'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        default=env_debug,
        help='Enable debug console output (DEBUG level: URLs, query details, etc.)'
    )
    parser.add_argument(
        '--progress',
        choices=['auto', 'on', 'off'],
        default=env_progress,
        help=f'Progress display mode: auto (detect best), on (force display), off (disable). (default: {env_progress})'
    )

    args = parser.parse_args()

    # Add additional configuration to args
    args.log_file = Path(env_log_file)
    
    # Determine console log level based on flags (priority: debug > verbose > default INFO)
    if args.debug:
        args.console_log_level = logging.DEBUG
    elif args.verbose:
        args.console_log_level = logging.INFO
    else:
        # Default to INFO so user sees progress (not silent)
        args.console_log_level = logging.INFO

    if args.download_workers < 1:
        logger.warning(
            f"--download-workers must be at least 1, got {args.download_workers}. Using default 1."
        )
        args.download_workers = 1


    # Resolve records directory from CLI or env
    if args.records_dir:
        records_dir_resolved = args.records_dir
    elif env_records_dir:
        records_dir_resolved = Path(env_records_dir)
    else:
        records_dir_resolved = None

    args.records_dir_resolved = records_dir_resolved

    return args
