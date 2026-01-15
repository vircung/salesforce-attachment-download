#!/usr/bin/env python3
"""
Salesforce Attachments Downloader - Main Entry Point

Runs the CSV-based workflow:
1. Query attachments using sf CLI with record IDs from CSV files
2. Download attachment files using REST API
"""

import sys
import logging

from src.cli.config import parse_arguments
from src.workflows.csv_records import process_csv_records_workflow
from src.logging import LoggingManager
from src.progress import ProgressTracker
from src.progress.core import ProgressMode

logger = logging.getLogger(__name__)


def main():
    """
    Main entry point - parse config and execute CSV-based workflow.

    Returns:
        Exit code: 0 for success, 2 for fatal errors
    """
    # Parse arguments and load configuration
    args = parse_arguments()

    # Setup logging with progress-aware management
    logging_manager = LoggingManager.get_instance()
    logging_manager.setup(args.log_file, console_level=args.console_log_level)

    try:
        # Validate required records directory
        if not args.records_dir_resolved:
            logger.error("Error: --records-dir is required")
            logger.error("Usage: python main.py --org <org> --records-dir <path>")
            return 2

        # Initialize progress tracker based on CLI argument
        progress_mode = ProgressMode(args.progress)
        progress_tracker = ProgressTracker(mode=progress_mode)
        
        # Connect logging and progress systems before starting
        progress_tracker.set_logging_manager(logging_manager)
        
        # Execute entire workflow with progress tracking context
        with progress_tracker:
            # Initial header (suppressed in progress mode)
            logger.info("=" * 70)
            logger.info("SALESFORCE ATTACHMENTS DOWNLOADER - CSV WORKFLOW")
            logger.info("=" * 70)
            
            # Execute CSV-based workflow
            stats = process_csv_records_workflow(
                org_alias=args.org,
                output_dir=args.output,
                records_dir=args.records_dir_resolved,
                batch_size=args.batch_size,
                download=True,
                progress_tracker=progress_tracker
            )

            # Final summary - use Rich display in progress mode, regular logging otherwise
            if progress_tracker.mode == ProgressMode.OFF:
                # Traditional logging when progress is disabled
                logger.info("=" * 70)
                logger.info("WORKFLOW COMPLETE")
                logger.info("=" * 70)
                logger.info(f"CSV files processed: {stats['total_csv_files']}")
                logger.info(f"Total records: {stats['total_records']}")
                logger.info(f"Total attachments: {stats['total_attachments']}")
            else:
                # Rich success panel when progress mode is active
                progress_tracker.display_completion_summary(stats)
                
                # Still log to file but suppress console output
                logger.info("=" * 70)
                logger.info("WORKFLOW COMPLETE")
                logger.info("=" * 70)
                logger.info(f"CSV files processed: {stats['total_csv_files']}")
                logger.info(f"Total records: {stats['total_records']}")
                logger.info(f"Total attachments: {stats['total_attachments']}")

        return 0

    except FileNotFoundError as e:
        logger.error(f"File or directory not found: {e}")
        logger.error("Please check that all required files and directories exist")
        logger.debug("Full error details:", exc_info=True)
        return 2
    
    except PermissionError as e:
        logger.error(f"Permission denied: {e}")
        logger.error("Please check file and directory permissions")
        logger.debug("Full error details:", exc_info=True)
        return 2
    
    except ValueError as e:
        logger.error(f"Invalid configuration or data: {e}")
        logger.error("Please check your CSV files and configuration settings")
        logger.debug("Full error details:", exc_info=True)
        return 2
    
    except KeyboardInterrupt:
        logger.warning("\nWorkflow interrupted by user (Ctrl+C)")
        logger.info("Exiting gracefully...")
        return 130  # Standard exit code for SIGINT
    
    except Exception as e:
        logger.error(f"Unexpected error occurred: {e}")
        logger.error("Please check the log file for detailed error information")
        logger.debug("Full error details:", exc_info=True)
        return 2


if __name__ == '__main__':
    sys.exit(main())
