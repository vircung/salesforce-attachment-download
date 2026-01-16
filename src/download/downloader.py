"""
Attachment Downloader

Main orchestration module to download Salesforce attachments
based on CSV metadata file.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Event
from typing import Dict, Any, Optional, Iterable, Tuple

from src.api.sf_auth import get_sf_auth_info
from src.api.sf_client import SalesforceClient
from src.exceptions import SFAuthError, SFAPIError, SFNetworkError
from src.query.filters import ParentIdFilter, apply_parent_id_filter, log_filter_summary

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


def download_attachments(
    metadata_csv: Path,
    output_dir: Path,
    org_alias: Optional[str] = None,
    filter_config: Optional[ParentIdFilter] = None,
    progress_stage: Optional[Any] = None,
    download_workers: int = 1,
    batch_size: int = 100
) -> Dict[str, Any]:
    """
    Main function to download all attachments from metadata CSV.

    Args:
        metadata_csv: Path to CSV file with attachment metadata
        output_dir: Directory to save downloaded files
        org_alias: Optional Salesforce org alias (uses default org if None)
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
            logger.info(f"Downloading {stats.total} attachment(s)...")
 
            output_dir.mkdir(parents=True, exist_ok=True)

            # Initialize progress tracking if provided

            if progress_stage:
                try:
                    progress_stage.start_downloads(stats.total)
                except Exception as e:
                    logger.warning(f"Failed to initialize progress tracking: {e}")
                    progress_stage = None

            if stats.total == 0:
                return stats.to_dict()

            if download_workers < 1:
                logger.warning(
                    f"Download workers must be at least 1, got {download_workers}. Using 1."
                )
                download_workers = 1


            if batch_size < 1:
                logger.warning(f"Batch size must be at least 1, got {batch_size}. Using 100.")
                batch_size = 100

            stats.total = len(attachments)
            fatal_error: Optional[Exception] = None
            stop_event = Event()
            processed_files = 0
            success_count = 0
            failed_count = 0
            skipped_count = 0
            bytes_transferred = 0
            total_buckets = max(1, (len(attachments) + batch_size - 1) // batch_size)

            def iter_buckets(items: list[dict[str, str]], size: int) -> Iterable[list[dict[str, str]]]:
                for idx in range(0, len(items), size):
                    yield items[idx:idx + size]

            def validate_output_path(path: Path, original_name: str) -> Optional[str]:
                try:
                    resolved_path = path.resolve()
                    resolved_output_dir = output_dir.resolve()

                    # Avoid string-prefix checks; ensure resolved_path is within output_dir.
                    try:
                        resolved_path.relative_to(resolved_output_dir)
                    except ValueError:
                        logger.error(f"Path traversal attempt detected: {original_name}")
                        return 'Path traversal validation failed'
                except (OSError, ValueError) as e:
                    logger.error(f"Path validation error for {original_name}: {e}")
                    return f"Path validation error: {e}"
                return None

            def record_error(attachment_id: str, original_name: str, message: str) -> None:
                stats.errors.append({
                    'id': attachment_id,
                    'name': original_name,
                    'error': message
                })

            def build_download_item(attachment: dict[str, str]) -> Tuple[dict[str, str], Path, str]:
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

                return attachment, output_path, original_name

            def download_single(attachment: dict[str, str], output_path: Path, original_name: str) -> Dict[str, Any]:
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

            def process_bucket(bucket: list[dict[str, str]], bucket_index: int) -> None:
                nonlocal processed_files, success_count, failed_count, skipped_count, bytes_transferred, fatal_error
                bucket_label = f"bucket {bucket_index}/{total_buckets}"
                bucket_success = 0
                bucket_failed = 0
                bucket_skipped = 0

                if progress_stage:
                    try:
                        progress_stage.update_download(
                            completed_files=processed_files,
                            current_file="bucket start",
                            bucket=bucket_label,
                            success_count=success_count,
                            failed_count=failed_count,
                            skipped_count=skipped_count,
                            bytes_transferred=bytes_transferred
                        )
                    except Exception:
                        pass

                logger.info(f"Processing {bucket_label} ({len(bucket)} files)")

                with ThreadPoolExecutor(max_workers=download_workers) as executor:
                    future_to_attachment = {}
                    for attachment in bucket:
                        if stop_event.is_set():
                            break
                        item, output_path, original_name = build_download_item(attachment)
                        future = executor.submit(download_single, item, output_path, original_name)
                        future_to_attachment[future] = (item, original_name)

                    for future in as_completed(future_to_attachment):
                        if stop_event.is_set():
                            for pending_future in future_to_attachment:
                                if not pending_future.done():
                                    pending_future.cancel()
                            break
                        attachment, attachment_name = future_to_attachment[future]
                        attachment_id = attachment.get('Id', 'unknown')
                        try:
                            result = future.result()
                        except Exception as exc:
                            failed_count += 1
                            bucket_failed += 1
                            record_error(attachment_id, attachment_name, str(exc))
                            logger.error(f"  ✗ Error: {exc}")
                            processed_files += 1
                            continue

                        status = result.get('status')
                        result_bytes = result.get('bytes_downloaded', 0) or 0
                        bytes_transferred += result_bytes

                        if status == 'success':
                            success_count += 1
                            bucket_success += 1
                        elif status == 'skipped':
                            skipped_count += 1
                            bucket_skipped += 1
                        elif status == 'fatal':
                            failed_count += 1
                            bucket_failed += 1
                            record_error(attachment_id, attachment_name, result.get('error', 'Fatal error'))
                            fatal_error = result.get('fatal_error')
                            stop_event.set()
                            for pending_future in future_to_attachment:
                                if not pending_future.done():
                                    pending_future.cancel()
                            break
                        else:
                            failed_count += 1
                            bucket_failed += 1
                            record_error(attachment_id, attachment_name, result.get('error', 'Download error'))

                        processed_files += 1

                        if progress_stage:
                            try:
                                progress_stage.update_download(
                                    completed_files=processed_files,
                                    current_file=attachment_name,
                                    bucket=bucket_label,
                                    success_count=success_count,
                                    failed_count=failed_count,
                                    skipped_count=skipped_count,
                                    bytes_transferred=bytes_transferred
                                )
                            except Exception:
                                pass

                logger.info(
                    f"Completed {bucket_label}: {bucket_success} downloaded, {bucket_skipped} skipped, {bucket_failed} failed"
                )

                if progress_stage:
                    try:
                        progress_stage.update_download(
                            completed_files=processed_files,
                            current_file="bucket complete",
                            bucket=bucket_label,
                            success_count=success_count,
                            failed_count=failed_count,
                            skipped_count=skipped_count,
                            bytes_transferred=bytes_transferred
                        )
                    except Exception:
                        pass

            bucket_index = 0
            for bucket in iter_buckets(attachments, batch_size):
                if stop_event.is_set():
                    break
                bucket_index += 1
                process_bucket(bucket, bucket_index)
                if fatal_error:
                    break

            stats.success = success_count
            stats.failed = failed_count
            stats.skipped = skipped_count

            if fatal_error:
                raise fatal_error

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


