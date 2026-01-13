"""
Attachment Downloader

Main orchestration script to download Salesforce attachments
based on CSV metadata file.
"""

import csv
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional

from src.api.sf_auth import get_sf_auth_info, SFAuthError
from src.api.sf_client import SalesforceClient, SFAPIError
from src.query.filters import ParentIdFilter, apply_parent_id_filter, log_filter_summary
from src.utils import log_section_header


def setup_logging(log_file: Path) -> None:
    """
    Configure logging to file and console.

    Args:
        log_file: Path to the log file where logs will be written
    """
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )


logger = logging.getLogger(__name__)

# Maximum filename length supported by most filesystems
MAX_FILENAME_LENGTH = 255


@dataclass
class DownloadStats:
    """Statistics for attachment download operations."""
    total: int = 0
    success: int = 0
    failed: int = 0
    skipped: int = 0
    errors: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for backward compatibility."""
        return {
            'total': self.total,
            'success': self.success,
            'failed': self.failed,
            'skipped': self.skipped,
            'errors': self.errors
        }


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to be filesystem-safe.

    Removes or replaces characters that may cause issues on
    Windows, Linux, or macOS filesystems. Also truncates filenames
    that exceed the maximum length.

    Args:
        filename: Original filename to sanitize

    Returns:
        Sanitized filename safe for filesystem use
    """
    # Replace problematic characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')

    # Limit length to maximum supported by most filesystems
    if len(filename) > MAX_FILENAME_LENGTH:
        name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
        max_name_length = MAX_FILENAME_LENGTH - len(ext) - 1
        filename = name[:max_name_length] + '.' + ext if ext else name[:MAX_FILENAME_LENGTH]

    return filename


def read_metadata_csv(csv_path: Path) -> List[Dict[str, str]]:
    """
    Read attachment metadata from CSV file.

    Expected columns: Id, Name, ContentType, BodyLength, ParentId, etc.

    Args:
        csv_path: Path to CSV file containing attachment metadata

    Returns:
        List of dictionaries with attachment metadata

    Raises:
        FileNotFoundError: If CSV file does not exist
        ValueError: If CSV is missing required columns (Id, Name)
    """
    logger.info(f"Reading metadata from: {csv_path}")

    if not csv_path.exists():
        raise FileNotFoundError(
            f"Metadata CSV file not found at path: {csv_path.absolute()}. "
            f"Please ensure the file exists and the path is correct."
        )

    attachments = []
    with csv_path.open('r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        # Validate required columns
        required_cols = ['Id', 'Name']
        if not all(col in reader.fieldnames for col in required_cols):
            raise ValueError(f"CSV missing required columns: {required_cols}")

        for row in reader:
            attachments.append(row)

    logger.info(f"Found {len(attachments)} attachments in metadata")
    return attachments


def download_attachments(
    metadata_csv: Path,
    output_dir: Path,
    org_alias: Optional[str] = None,
    chunk_size: int = 8192,
    filter_config: Optional[ParentIdFilter] = None
) -> Dict[str, Any]:
    """
    Main function to download all attachments from metadata CSV.

    Args:
        metadata_csv: Path to CSV file with attachment metadata
        output_dir: Directory to save downloaded files
        org_alias: Optional Salesforce org alias (uses default org if None)
        chunk_size: Download chunk size in bytes (default: 8192)
        filter_config: Optional filter configuration for ParentId filtering

    Returns:
        Dictionary with summary statistics including:
        - total: Total number of attachments processed
        - success: Number of successful downloads
        - skipped: Number of files skipped (already exist)
        - failed: Number of failed downloads
        - errors: List of error details for failed downloads

    Raises:
        SFAuthError: If Salesforce authentication fails
        FileNotFoundError: If metadata file is not found
        Exception: For other unexpected errors during processing
    """
    stats = DownloadStats()

    try:
        # Step 1: Get SF authentication
        log_section_header("STEP 1: Retrieving Salesforce authentication")

        auth_info = get_sf_auth_info(org_alias)
        logger.info(f"Authenticated as: {auth_info['username']}")

        # Step 2: Initialize SF client
        log_section_header("STEP 2: Initializing Salesforce API client")

        with SalesforceClient(
            access_token=auth_info['access_token'],
            instance_url=auth_info['instance_url'],
            api_version=auth_info['api_version']
        ) as client:

            # Step 3: Read metadata
            log_section_header("STEP 3: Reading attachment metadata")

            attachments = read_metadata_csv(metadata_csv)
            original_count = len(attachments)

            # Step 3.5: Apply filtering if configured
            if filter_config and filter_config.has_filters() and filter_config.strategy == 'python':
                log_section_header("STEP 3.5: Applying ParentId filter")

                attachments = apply_parent_id_filter(attachments, filter_config)
                log_filter_summary(original_count, len(attachments), filter_config)

                # If no attachments match, exit gracefully
                if len(attachments) == 0:
                    logger.warning("No attachments matched the filter criteria. Skipping download phase.")
                    stats.total = 0
                    return stats.to_dict()

            stats.total = len(attachments)

            # Step 4: Download files
            log_section_header(f"STEP 4: Downloading {stats.total} attachments", width=60)

            output_dir.mkdir(parents=True, exist_ok=True)

            for idx, attachment in enumerate(attachments, 1):
                attachment_id = attachment['Id']
                original_name = attachment['Name']

                # Sanitize filename and construct output path
                safe_name = sanitize_filename(original_name)

                # Include ID prefix to ensure uniqueness
                output_filename = f"{attachment_id}_{safe_name}"
                output_path = output_dir / output_filename

                # Path traversal validation
                try:
                    resolved_path = output_path.resolve()
                    resolved_output_dir = output_dir.resolve()
                    if not str(resolved_path).startswith(str(resolved_output_dir)):
                        logger.error(f"Path traversal attempt detected: {original_name}")
                        stats.failed += 1
                        stats.errors.append({
                            'id': attachment_id,
                            'name': original_name,
                            'error': 'Path traversal validation failed'
                        })
                        continue
                except (OSError, ValueError) as e:
                    logger.error(f"Path validation error for {original_name}: {e}")
                    stats.failed += 1
                    stats.errors.append({
                        'id': attachment_id,
                        'name': original_name,
                        'error': f'Path validation error: {e}'
                    })
                    continue

                logger.info(f"[{idx}/{stats.total}] Processing: {original_name}")

                # Check if file already exists
                if output_path.exists():
                    logger.info(f"  ⊙ Skipped (already exists): {output_path.name}")
                    stats.skipped += 1
                    continue

                try:
                    # Download with progress indication using configured chunk size
                    client.download_attachment(attachment_id, output_path, chunk_size=chunk_size)
                    stats.success += 1
                    logger.info(f"  ✓ Success: {output_path.name}")

                except SFAPIError as e:
                    stats.failed += 1
                    error_msg = str(e)
                    stats.errors.append({
                        'id': attachment_id,
                        'name': original_name,
                        'error': error_msg
                    })
                    logger.error(f"  ✗ Error: {error_msg}")
                    continue

        # Step 5: Summary
        log_section_header("DOWNLOAD SUMMARY", width=60)
        logger.info(f"Total attachments: {stats.total}")
        logger.info(f"Downloaded: {stats.success}")
        logger.info(f"Skipped (already exists): {stats.skipped}")
        logger.info(f"Failed: {stats.failed}")

        if stats.errors:
            logger.warning("\nFailed downloads:")
            for error in stats.errors:
                logger.warning(f"  - {error['name']} (ID: {error['id']}): {error['error']}")

        return stats.to_dict()

    except SFAuthError as e:
        logger.error(f"Authentication failed: {e}")
        raise

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        raise

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise


def main():
    """
    Main entry point for the downloader script.

    Parses command-line arguments and orchestrates the attachment
    download process.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description='Download Salesforce attachments from metadata CSV'
    )
    parser.add_argument(
        '--metadata',
        type=Path,
        required=True,
        help='Path to CSV file with attachment metadata'
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=Path('./output/files'),
        help='Directory to save downloaded files (default: ./output/files)'
    )
    parser.add_argument(
        '--org',
        type=str,
        help='Salesforce org alias (default: use default org)'
    )
    parser.add_argument(
        '--log-file',
        type=Path,
        default=Path('./logs/download.log'),
        help='Log file path (default: ./logs/download.log)'
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.log_file)

    logger.info("Starting Salesforce Attachments Downloader")
    logger.info(f"Metadata CSV: {args.metadata}")
    logger.info(f"Output directory: {args.output}")
    logger.info(f"Org alias: {args.org or 'default'}")

    try:
        stats = download_attachments(
            metadata_csv=args.metadata,
            output_dir=args.output,
            org_alias=args.org
        )

        # Exit code based on results
        if stats['failed'] > 0:
            logger.warning("Some downloads failed - check errors above")
            sys.exit(1)
        else:
            logger.info("All downloads completed successfully!")
            sys.exit(0)

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(2)


if __name__ == '__main__':
    main()
