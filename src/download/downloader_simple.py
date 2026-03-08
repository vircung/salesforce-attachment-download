"""
Simple-Salesforce Attachment Downloader

This module provides attachment download functionality using simple-salesforce
instead of direct REST API calls, for better error handling and consistency.
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, Any, List, Optional

from simple_salesforce.api import Salesforce

from src.api.sf_connection import SalesforceConnectionPool
from src.api.sf_error_handler import SalesforceErrorHandler
from src.api.usage_monitor import SalesforceUsageMonitor
from src.exceptions import SFAuthError, SFAPIError, SFNetworkError

logger = logging.getLogger(__name__)

DEFAULT_CONNECT_TIMEOUT = 10
DEFAULT_READ_TIMEOUT = 60
DEFAULT_TMP_DIR_NAME = ".tmp_downloads"


def _write_skipped_files_report(
    os_errors: List[Dict[str, Any]],
    output_dir: Path,
    sf_client: Salesforce
) -> None:
    """Write a JSON report of files skipped due to OS errors (e.g. filename too long).

    Written to the top-level output/ directory so it aggregates across all objects.
    Includes a manual download URL for each file so the user can retrieve them.
    """
    # output_dir is e.g. output/ObjectName/files/ — go up to output/
    report_dir = output_dir
    for _ in range(3):
        if report_dir.name == 'output':
            break
        report_dir = report_dir.parent
    report_path = report_dir / "skipped_files.json"

    instance_url = sf_client.sf_instance if hasattr(sf_client, 'sf_instance') else ''
    if instance_url and not instance_url.startswith('https://'):
        instance_url = f"https://{instance_url}"

    # Load existing report if present (multiple objects may append)
    existing_entries = []
    if report_path.exists():
        try:
            with open(report_path, 'r', encoding='utf-8') as f:
                existing_entries = json.load(f)
        except (json.JSONDecodeError, OSError):
            existing_entries = []

    new_entries = []
    for err in os_errors:
        attachment_id = err.get('id', '')
        new_entries.append({
            'attachment_id': attachment_id,
            'parent_id': err.get('parent_id', ''),
            'original_name': err.get('name', ''),
            'error': err.get('error', ''),
            'manual_download_url': f"{instance_url}/servlet/servlet.FileDownload?file={attachment_id}" if instance_url else '',
        })

    # Deduplicate by attachment_id
    merged = existing_entries + new_entries
    seen_ids = set()
    all_entries = []
    for entry in merged:
        aid = entry.get('attachment_id', '')
        if aid and aid in seen_ids:
            continue
        seen_ids.add(aid)
        all_entries.append(entry)

    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(all_entries, f, indent=2, ensure_ascii=False)

        logger.warning(
            f"Wrote skipped files report ({len(new_entries)} new, {len(all_entries)} total): {report_path}"
        )
    except Exception as e:
        logger.error(f"Failed to write skipped files report: {e}")


def download_attachment_simple_salesforce(
    attachment_id: str,
    output_path: Path,
    sf_client: Salesforce,
    error_handler: Optional[SalesforceErrorHandler] = None,
    usage_monitor: Optional[SalesforceUsageMonitor] = None,
    chunk_size: int = 8192
) -> int:
    """
    Download an attachment file using simple-salesforce.

    Args:
        attachment_id: Salesforce Attachment ID
        output_path: Local file path to save downloaded content
        sf_client: Authenticated simple-salesforce client
        error_handler: Optional error handler for retry logic
        usage_monitor: Optional usage monitor for tracking
        chunk_size: Size of chunks for streaming download

    Returns:
        Number of bytes downloaded

    Raises:
        SFAPIError: If download fails
        SFAuthError: If authentication fails
        SFNetworkError: If network error occurs
    """
    # Track API call start
    start_time = None
    if usage_monitor:
        start_time = usage_monitor.stats.last_call_time or 0

    try:
        # Use error handler if provided
        if error_handler:
            def download_operation():
                return _download_attachment_internal(attachment_id, output_path, sf_client, chunk_size)

            bytes_downloaded = error_handler.execute_with_retry(download_operation)
        else:
            bytes_downloaded = _download_attachment_internal(attachment_id, output_path, sf_client, chunk_size)

        # Track successful API call
        if usage_monitor:
            call_time = usage_monitor.stats.last_call_time or 0
            response_time = call_time - start_time if start_time else None
            usage_monitor.track_call('download', response_time, success=True)

        return bytes_downloaded

    except Exception as e:
        # Track failed API call
        if usage_monitor:
            call_time = usage_monitor.stats.last_call_time or 0
            response_time = call_time - start_time if start_time else None
            usage_monitor.track_call('download', response_time, success=False)

        logger.error(f"Download failed for attachment {attachment_id}: {e}")
        raise


def _download_attachment_internal(
    attachment_id: str,
    output_path: Path,
    sf_client: Salesforce,
    chunk_size: int = 8192
) -> int:
    """
    Internal download implementation using simple-salesforce.

    Args:
        attachment_id: Salesforce Attachment ID
        output_path: Local file path to save downloaded content
        sf_client: Authenticated simple-salesforce client
        chunk_size: Size of chunks for streaming download

    Returns:
        Number of bytes downloaded
    """
    logger.debug(f"Downloading attachment: {attachment_id}")

    # Never overwrite an existing file
    if output_path.exists():
        logger.debug(f"File already exists, skipping: {output_path.name}")
        return 0

    # Create parent directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)

    temp_dir_path = output_path.parent.parent / DEFAULT_TMP_DIR_NAME
    temp_dir_path.mkdir(parents=True, exist_ok=True)

    # Download to temporary file first, then atomically replace
    temp_name = f"{output_path.name}.{attachment_id}.part"
    temp_path = temp_dir_path / temp_name

    bytes_downloaded = 0
    try:
        # Use simple-salesforce to get attachment data
        # Note: simple-salesforce doesn't have a direct download method,
        # so we construct the URL and use requests directly
        attachment_url = f"{sf_client.base_url}sobjects/Attachment/{attachment_id}/Body"

        # Get the attachment data using the session from simple-salesforce
        response = sf_client.session.get(attachment_url, stream=True)

        # Check for HTTP errors
        if response.status_code == 404:
            logger.error(f"Attachment not found: {attachment_id}")
            raise SFAPIError(f"Attachment {attachment_id} not found (404)")

        if response.status_code in (401, 403):
            logger.error(f"Authentication failed downloading {attachment_id}: {response.status_code}")
            raise SFAuthError(f"Authentication failed (HTTP {response.status_code})")

        if response.status_code >= 400:
            logger.error(f"Service error downloading {attachment_id}: {response.status_code}")
            raise SFNetworkError(f"Service error (HTTP {response.status_code})")

        response.raise_for_status()

        # Download to temp file
        with temp_path.open('wb') as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:  # Filter out keep-alive chunks
                    f.write(chunk)
                    bytes_downloaded += len(chunk)

        # Atomically move to final location
        os.replace(temp_path, output_path)

        logger.debug(f"Downloaded {bytes_downloaded} bytes to: {output_path.name}")
        return bytes_downloaded

    finally:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            pass


def download_attachments_simple_salesforce(
    metadata_csv: Path,
    output_dir: Path,
    org_alias: str,
    connection_pool: Optional[SalesforceConnectionPool] = None,
    error_handler: Optional[SalesforceErrorHandler] = None,
    usage_monitor: Optional[SalesforceUsageMonitor] = None,
    filter_config=None,
    progress_stage=None,
    completed_counter=None
) -> Dict[str, Any]:
    """
    Download all attachments from metadata CSV using simple-salesforce.

    Args:
        metadata_csv: Path to CSV file with attachment metadata
        output_dir: Directory to save downloaded files
        org_alias: Salesforce org alias
        connection_pool: Optional connection pool for client management
        error_handler: Optional error handler for retry logic
        usage_monitor: Optional usage monitor for tracking
        filter_config: Optional filter configuration (for compatibility)
        progress_stage: Optional progress tracking stage
        completed_counter: Optional shared counter for multi-worker progress

    Returns:
        Dictionary with download statistics
    """
    from .metadata import read_metadata_csv
    from .filename import (
        DEFAULT_PARENT_ID,
        detect_filename_collisions,
    )
    from .stats import DownloadStats

    stats = DownloadStats()

    # Get client from pool or create new one
    if connection_pool:
        sf_client = connection_pool.get_connection()
        try:
            result = _download_attachments_internal(
                metadata_csv, output_dir, sf_client, stats,
                error_handler, usage_monitor, filter_config,
                progress_stage, completed_counter
            )
            return result
        finally:
            connection_pool.return_connection(sf_client)
    else:
        # Fallback: create client directly
        from src.api.sf_auth_adapter import SFCLIAuthAdapter
        adapter = SFCLIAuthAdapter(org_alias)
        sf_client = adapter.get_client()

        return _download_attachments_internal(
            metadata_csv, output_dir, sf_client, stats,
            error_handler, usage_monitor, filter_config,
            progress_stage, completed_counter
        )


def _download_attachments_internal(
    metadata_csv: Path,
    output_dir: Path,
    sf_client: Salesforce,
    stats: 'DownloadStats',
    error_handler: Optional[SalesforceErrorHandler],
    usage_monitor: Optional[SalesforceUsageMonitor],
    filter_config,
    progress_stage,
    completed_counter
) -> Dict[str, Any]:
    """
    Internal implementation of attachment downloads.
    """
    from .metadata import read_metadata_csv
    from .filename import (
        DEFAULT_PARENT_ID,
        detect_filename_collisions,
        build_output_filename,
    )
    from .scan import scan_existing_files, load_skipped_attachment_ids
    from src.workflows.common import ensure_directories

    try:
        # 1. Read metadata
        logger.debug("Reading attachment metadata")
        attachments = read_metadata_csv(metadata_csv)
        original_count = len(attachments)

        # Apply filtering if configured
        if filter_config and hasattr(filter_config, 'has_filters') and filter_config.has_filters() and filter_config.strategy == 'python':
            logger.debug("Applying ParentId filter")
            from src.query.filters import apply_parent_id_filter, log_filter_summary
            attachments = apply_parent_id_filter(attachments, filter_config)
            log_filter_summary(original_count, len(attachments), filter_config)

            if len(attachments) == 0:
                logger.warning("No attachments matched the filter criteria. Skipping download phase.")
                stats.total = 0
                return stats.to_dict()

        # 2. Detect filename collisions
        logger.debug("Analyzing filename collisions")
        filename_info_map = detect_filename_collisions(attachments)
        logger.debug(f"Collision analysis complete for {len(attachments)} attachments")

        # Ensure output directory exists
        ensure_directories(output_dir)

        # Early exit if no attachments
        if len(attachments) == 0:
            stats.total = 0
            logger.info("No attachments to download")
            return stats.to_dict()

        # 3. Scan existing files on disk
        existing_filenames = scan_existing_files(output_dir)

        # 4. Load permanently-skipped attachment IDs
        skipped_ids = load_skipped_attachment_ids(output_dir)

        # 5-6. Build filenames and split into to_download vs skipped
        to_download = []
        skipped_existing = 0
        skipped_permanent = 0

        for attachment in attachments:
            attachment_id = attachment['Id']
            output_filename = build_output_filename(attachment, filename_info_map)

            if output_filename in existing_filenames:
                skipped_existing += 1
            elif attachment_id in skipped_ids:
                skipped_permanent += 1
            else:
                to_download.append(attachment)

        total_skipped = skipped_existing + skipped_permanent
        stats.skipped = total_skipped
        stats.total = len(to_download)

        logger.info(
            "Scan: %d existing, %d permanently skipped, %d to download (of %d total)",
            skipped_existing, skipped_permanent, len(to_download), len(attachments)
        )

        # 7. Adjust progress total
        if progress_stage and total_skipped > 0:
            try:
                progress_stage.adjust_total(total_skipped)
            except Exception:
                pass

        # Early exit if everything is already downloaded
        if not to_download:
            logger.info("All attachments already downloaded")
            return stats.to_dict()

        # 8. Download loop — only files that need downloading
        logger.info(f"Downloading {len(to_download)} attachment(s)...")

        for attachment in to_download:
            attachment_id = attachment['Id']
            parent_id = attachment.get('ParentId', DEFAULT_PARENT_ID)
            original_name = attachment['Name']
            output_filename = build_output_filename(attachment, filename_info_map)
            output_path = output_dir / output_filename

            try:
                result_bytes = download_attachment_simple_salesforce(
                    attachment_id, output_path, sf_client,
                    error_handler, usage_monitor
                )
                logger.info("  ✓ Downloaded")
                stats.success += 1
                stats.completed += 1
                stats.bytes_transferred += result_bytes

                # Update progress
                if progress_stage:
                    try:
                        if completed_counter:
                            with completed_counter['lock']:
                                completed_counter['count'] += 1
                                global_completed = completed_counter['count']
                        else:
                            global_completed = stats.completed

                        progress_stage.update_download(
                            completed_files=global_completed,
                            current_file=original_name,
                            success_count=stats.success,
                            failed_count=stats.failed,
                            skipped_count=stats.skipped,
                            bytes_transferred=stats.bytes_transferred
                        )
                    except Exception:
                        pass

            except (SFNetworkError, SFAuthError) as e:
                logger.error(f"  ✗ Fatal error: {e}")
                stats.failed += 1
                stats.completed += 1
                stats.errors.append({
                    'id': attachment_id,
                    'name': original_name,
                    'error': str(e)
                })
                if completed_counter:
                    with completed_counter['lock']:
                        completed_counter['count'] += 1
                raise e

            except SFAPIError as e:
                logger.error(f"  ✗ Error: {e}")
                stats.failed += 1
                stats.completed += 1
                stats.errors.append({
                    'id': attachment_id,
                    'name': original_name,
                    'error': str(e)
                })
                if completed_counter:
                    with completed_counter['lock']:
                        completed_counter['count'] += 1

            except OSError as e:
                logger.warning(
                    f"  ✗ OS error for attachment {attachment_id} "
                    f"('{original_name}'): {e} — skipping file"
                )
                stats.failed += 1
                stats.completed += 1
                stats.errors.append({
                    'id': attachment_id,
                    'parent_id': parent_id,
                    'name': original_name,
                    'error': str(e),
                    'error_type': 'OSError'
                })
                if completed_counter:
                    with completed_counter['lock']:
                        completed_counter['count'] += 1

        # Generate skipped-files report for OS errors (e.g. filename too long)
        os_errors = [e for e in stats.errors if e.get('error_type') == 'OSError']
        if os_errors:
            _write_skipped_files_report(os_errors, output_dir, sf_client)

        # Summary
        logger.info(
            f"Download complete: {stats.success} downloaded, {stats.skipped} skipped, {stats.failed} failed"
        )

        return stats.to_dict()

    except Exception as e:
        logger.error(f"Unexpected error during downloads: {e}")
        raise