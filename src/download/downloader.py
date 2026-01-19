"""
Attachment Downloader

Main orchestration module to download Salesforce attachments
based on CSV metadata file.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Optional, Iterable, Tuple

from src.api.sf_auth import get_sf_auth_info
from src.api.sf_client import SalesforceClient
from src.exceptions import SFAuthError, SFAPIError, SFNetworkError
from src.query.filters import ParentIdFilter, apply_parent_id_filter, log_filter_summary

from src.workflows.common import ensure_directories
from .stats import DownloadStats
from .metadata import read_metadata_csv
from .filename import (
    FilenameInfo,
    DEFAULT_PARENT_ID,
    sanitize_filename,
    detect_filename_collisions,
)


# Type hints for progress tracking
try:
    from src.progress.core.stage import ProgressStage
except ImportError:
    ProgressStage = None  # type: ignore

logger = logging.getLogger(__name__)





def download_single(
    attachment: dict[str, str],
    output_path: Path,
    original_name: str,
    client: SalesforceClient
) -> Dict[str, Any]:
    """
    Download a single attachment file.

    Args:
        attachment: Attachment metadata dictionary
        output_path: Path where to save the file
        original_name: Original filename for logging
        client: Salesforce API client

    Returns:
        Dictionary with download result status and metadata
    """
    attachment_id = attachment['Id']

    validation_error = validate_output_path(output_path, original_name)
    if validation_error:
        return {
            'status': 'failed',
            'name': original_name,
            'id': attachment_id,
            'error': validation_error,
            'bytes_downloaded': 0
        }

    if output_path.exists():
        logger.info("  ⊙ Skipped (already exists)")
        return {
            'status': 'skipped',
            'name': original_name,
            'id': attachment_id,
            'bytes_downloaded': 0
        }

    try:
        bytes_downloaded = client.download_attachment(
            attachment_id,
            output_path
        )
        logger.info("  ✓ Downloaded")
        return {
            'status': 'success',
            'name': original_name,
            'id': attachment_id,
            'bytes_downloaded': bytes_downloaded
        }
    except (SFNetworkError, SFAuthError) as e:
        logger.error(f"  ✗ Fatal error: {e}")
        return {
            'status': 'fatal',
            'name': original_name,
            'id': attachment_id,
            'error': str(e),
            'fatal_error': e,
            'bytes_downloaded': 0
        }
    except SFAPIError as e:
        logger.error(f"  ✗ Error: {e}")
        return {
            'status': 'failed',
            'name': original_name,
            'id': attachment_id,
            'error': str(e),
            'bytes_downloaded': 0
        }


def validate_output_path(path: Path, original_name: str) -> Optional[str]:
    """
    Validate that the output path is safe.

    Args:
        path: The output path to validate
        original_name: Original filename for logging

    Returns:
        Error message if validation fails, None if valid
    """
    try:
        resolved_path = path.resolve()
        # Check for basic path issues
        if '..' in str(path):
            logger.error(f"Path traversal attempt detected: {original_name}")
            return 'Path traversal validation failed'
    except (OSError, ValueError) as e:
        logger.error(f"Path validation error for {original_name}: {e}")
        return f"Path validation error: {e}"
    return None


def download_attachments(
    metadata_csv: Path,
    output_dir: Path,
    org_alias: Optional[str] = None,
    filter_config: Optional[ParentIdFilter] = None,
    progress_stage: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Main function to download all attachments from metadata CSV.

    Args:
        metadata_csv: Path to CSV file with attachment metadata
        output_dir: Directory to save downloaded files
        org_alias: Optional Salesforce org alias (uses default org if None)
        filter_config: Optional filter configuration for ParentId filtering
        progress_stage: Optional progress tracking stage.
               If provided, MUST be pre-initialized by caller with start_downloads().
               This function only updates progress, does not initialize it.

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
        logger.debug("Retrieving Salesforce authentication")

        auth_info = get_sf_auth_info(org_alias)
        logger.debug(f"Authenticated as: {auth_info['username']}")

        # Step 2: Initialize SF client
        logger.debug("Initializing Salesforce API client")

        with SalesforceClient(
            access_token=auth_info['access_token'],
            instance_url=auth_info['instance_url'],
            api_version=auth_info['api_version']
        ) as client:

            # Step 3: Read metadata
            logger.debug("Reading attachment metadata")

            attachments = read_metadata_csv(metadata_csv)
            original_count = len(attachments)

            # Step 3.5: Apply filtering if configured
            if filter_config and filter_config.has_filters() and filter_config.strategy == 'python':
                logger.debug("Applying ParentId filter")

                attachments = apply_parent_id_filter(attachments, filter_config)
                log_filter_summary(original_count, len(attachments), filter_config)

                # If no attachments match, exit gracefully
                if len(attachments) == 0:
                    logger.warning("No attachments matched the filter criteria. Skipping download phase.")
                    stats.total = 0
                    return stats.to_dict()

            stats.total = len(attachments)

            # Step 3.6: Detect filename collisions
            logger.debug("Analyzing filename collisions")

            filename_info_map = detect_filename_collisions(attachments)
            logger.debug(f"Collision analysis complete for {len(attachments)} attachments")

            # Step 4: Download files
   
            ensure_directories(output_dir)

            # Early exit if no attachments
            if stats.total == 0:
                logger.info("No attachments to download")
                return stats.to_dict()

            # Step 4: Download files sequentially
            logger.info(f"Downloading {stats.total} attachment(s)...")

            for attachment in attachments:
                attachment_id = attachment['Id']
                parent_id = attachment.get('ParentId', DEFAULT_PARENT_ID)
                original_name = attachment['Name']

                filename_info = filename_info_map.get(attachment_id)
                if filename_info:
                    safe_name = filename_info.safe_name
                    has_collision = filename_info.has_collision
                else:
                    safe_name = sanitize_filename(original_name)
                    has_collision = False

                if has_collision:
                    output_filename = f"{parent_id}_{attachment_id}_{safe_name}"
                else:
                    output_filename = f"{parent_id}_{safe_name}"

                output_path = output_dir / output_filename

                try:
                    result = download_single(attachment, output_path, original_name, client)

                    stats.completed += 1
                    result_bytes = result.get('bytes_downloaded', 0) or 0
                    stats.bytes_transferred += result_bytes

                    if result['status'] == 'success':
                        stats.success += 1
                    elif result['status'] == 'skipped':
                        stats.skipped += 1
                    elif result['status'] == 'fatal':
                        stats.failed += 1
                        stats.errors.append({
                            'id': attachment_id,
                            'name': original_name,
                            'error': result.get('error', 'Fatal error')
                        })
                        raise result.get('fatal_error', Exception("Fatal error"))
                    else:
                        stats.failed += 1
                        stats.errors.append({
                            'id': attachment_id,
                            'name': original_name,
                            'error': result.get('error', 'Download error')
                        })

                    # Update progress
                    if progress_stage:
                        try:
                            progress_stage.update_download(
                                completed_files=stats.completed,
                                current_file=original_name,
                                success_count=stats.success,
                                failed_count=stats.failed,
                                skipped_count=stats.skipped,
                                bytes_transferred=stats.bytes_transferred
                            )
                        except Exception:
                            pass

                except Exception as e:
                    stats.failed += 1
                    stats.completed += 1
                    stats.errors.append({
                        'id': attachment_id,
                        'name': original_name,
                        'error': str(e)
                    })

        # Summary (keep as INFO - important for user)
        logger.info(
            f"Download complete: {stats.success} downloaded, {stats.skipped} skipped, {stats.failed} failed"
        )

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


