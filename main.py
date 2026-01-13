#!/usr/bin/env python3
"""
Salesforce Attachments Extract - Main Entry Point

Runs the complete workflow:
1. Query attachments using sf CLI
2. Download attachment files using REST API
"""

import sys
import logging

from src.cli.config import parse_arguments
from src.workflows.csv_records import process_csv_records_workflow
from src.workflows.standard import process_standard_workflow
from src.download.downloader import setup_logging

logger = logging.getLogger(__name__)


def main():
    """
    Main entry point - parse config and route to appropriate workflow.

    Returns:
        Exit code: 0 for success, 1 for failures, 2 for fatal errors
    """
    # Parse arguments and load configuration
    args = parse_arguments()

    # Setup logging
    setup_logging(args.log_file)

    logger.info("=" * 70)
    logger.info("SALESFORCE ATTACHMENTS EXTRACT - POC")
    logger.info("=" * 70)

    try:
        # Route to appropriate workflow
        if args.use_csv_mode:
            logger.info("")
            stats = process_csv_records_workflow(
                org_alias=args.org,
                output_dir=args.output,
                records_dir=args.records_dir_resolved,
                batch_size=args.batch_size,
                download=True
            )

            # Final summary
            logger.info("=" * 70)
            logger.info("WORKFLOW COMPLETE")
            logger.info("=" * 70)
            logger.info(f"CSV files processed: {stats['total_csv_files']}")
            logger.info(f"Total records: {stats['total_records']}")
            logger.info(f"Total attachments: {stats['total_attachments']}")
            logger.info("")

            return 0
        else:
            # Standard workflow
            stats = process_standard_workflow(args, chunk_size=args.chunk_size)
            return 0 if stats['failed'] == 0 else 1

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 2


if __name__ == '__main__':
    sys.exit(main())
