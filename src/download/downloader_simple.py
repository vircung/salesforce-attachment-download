"""
Simple-Salesforce Attachment Downloader

Single-file download and per-batch download functions.
"""

import logging
import os
from pathlib import Path
from typing import Dict, Any, List, Optional

from simple_salesforce.api import Salesforce

from src.models import AttachmentRecord
from src.api.sf_connection import SalesforceConnectionPool
from src.api.sf_error_handler import SalesforceErrorHandler
from src.api.usage_monitor import SalesforceUsageMonitor
from src.download.filename import FilenameInfo, build_output_filename, check_filename_length
from src.download.stats import DownloadStats
from src.exceptions import SFAuthError, SFAPIError, SFNetworkError
from src.progress.stages import DownloadStage
from src.progress.worker_tracker import WorkerActivityTracker

from src.config_limits import HttpTimeout, FileSystem

logger = logging.getLogger(__name__)

DEFAULT_CONNECT_TIMEOUT = HttpTimeout.CONNECT
DEFAULT_READ_TIMEOUT = HttpTimeout.READ
DEFAULT_TMP_DIR_NAME = FileSystem.TMP_DIR_NAME


def download_attachment_simple_salesforce(
    attachment_id: str,
    output_path: Path,
    sf_client: Salesforce,
    error_handler: Optional[SalesforceErrorHandler] = None,
    usage_monitor: Optional[SalesforceUsageMonitor] = None,
    chunk_size: int = FileSystem.DOWNLOAD_CHUNK_SIZE
) -> int:
    """
    Download an attachment file using simple-salesforce.

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
    chunk_size: int = FileSystem.DOWNLOAD_CHUNK_SIZE
) -> int:
    """
    Internal download implementation using simple-salesforce.

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

    temp_dir_path = output_path.parent / DEFAULT_TMP_DIR_NAME
    temp_dir_path.mkdir(parents=True, exist_ok=True)

    # Download to temporary file first, then atomically replace
    temp_name = f"{output_path.name}.{attachment_id}.part"
    temp_path = temp_dir_path / temp_name

    bytes_downloaded = 0
    try:
        attachment_url = f"{sf_client.base_url}sobjects/Attachment/{attachment_id}/Body"

        response = sf_client.session.get(
            attachment_url,
            stream=True,
            timeout=(DEFAULT_CONNECT_TIMEOUT, DEFAULT_READ_TIMEOUT),
        )

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
                if chunk:
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


def download_batch(
    attachments: List[AttachmentRecord],
    output_dir: Path,
    filename_info_map: Dict[str, FilenameInfo],
    connection_pool: SalesforceConnectionPool,
    error_handler: Optional[SalesforceErrorHandler],
    usage_monitor: Optional[SalesforceUsageMonitor],
    progress_stage: Optional[DownloadStage],
    completed_counter: Optional[dict],
    worker_tracker: Optional[WorkerActivityTracker] = None,
    task_id: str = "",
    object_name: str = "",
    batch_idx: int = 0,
    report_entries: Optional[dict] = None,
    instance_url: str = "",
) -> Dict[str, Any]:
    """Download a batch of attachments from in-memory data.

    Gets a connection from the pool, iterates over attachments,
    downloads each one, and returns aggregated stats.

    Fatal errors (SFNetworkError, SFAuthError) are re-raised.
    OSError per file is caught and recorded.

    Args:
        report_entries: Shared mutable container {'entries': [], 'lock': Lock()}
            for preserving report data across fatal errors.
        instance_url: Salesforce instance URL for download_url construction.

    Returns:
        DownloadStats.to_dict() with added 'downloaded_entries' key
    """
    if worker_tracker and task_id:
        worker_tracker.register_task(
            task_id, "Download", object_name, batch_idx, len(attachments)
        )

    stats = DownloadStats()
    stats.total = len(attachments)
    downloaded_entries: List[Dict[str, Any]] = []

    def _make_download_url(attachment_id: str) -> str:
        if instance_url:
            return f"{instance_url}/servlet/servlet.FileDownload?file={attachment_id}"
        return ""

    def _append_to_report(entry: Dict[str, Any]) -> None:
        """Append entry to shared report_entries under lock."""
        if report_entries is not None:
            with report_entries['lock']:
                report_entries['entries'].append(entry)

    sf_client = connection_pool.get_connection()
    try:
        for file_idx, attachment in enumerate(attachments):
            output_filename = build_output_filename(attachment, filename_info_map)
            output_path = output_dir / output_filename

            # Update worker tracker with current file
            if worker_tracker and task_id:
                worker_tracker.update_task(
                    task_id, file_idx, "downloading", attachment.name
                )

            try:
                # Check filename length before attempting download
                if not check_filename_length(output_path, attachment.id):
                    raise OSError(
                        f"Filename too long for filesystem: {output_filename}"
                    )

                result_bytes = download_attachment_simple_salesforce(
                    attachment.id, output_path, sf_client,
                    error_handler, usage_monitor
                )
                stats.success += 1
                stats.completed += 1
                stats.bytes_transferred += result_bytes

                # Record downloaded entry
                dl_entry = {
                    'attachment_id': attachment.id,
                    'parent_id': attachment.parent_id,
                    'filename': output_filename,
                    'object_name': object_name,
                    'download_url': _make_download_url(attachment.id),
                    'body_length': attachment.body_length,
                }
                downloaded_entries.append(dl_entry)
                _append_to_report(dl_entry)

                # Update worker tracker after successful download
                if worker_tracker and task_id:
                    worker_tracker.update_task(
                        task_id, file_idx + 1, "downloading", attachment.name
                    )

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
                            current_file=attachment.name,
                            success_count=stats.success,
                            failed_count=stats.failed,
                            skipped_count=stats.skipped,
                            bytes_transferred=stats.bytes_transferred
                        )
                    except Exception:
                        pass

            except (SFNetworkError, SFAuthError) as e:
                logger.error(f"Fatal error downloading {attachment.id}: {e}")
                error_type = 'SFAuthError' if isinstance(e, SFAuthError) else 'SFNetworkError'
                stats.failed += 1
                stats.completed += 1
                err_entry = {
                    'id': attachment.id,
                    'parent_id': attachment.parent_id,
                    'name': attachment.name,
                    'error': str(e),
                    'error_type': error_type,
                    'output_filename': output_filename,
                }
                stats.errors.append(err_entry)
                _append_to_report({
                    'attachment_id': attachment.id,
                    'parent_id': attachment.parent_id,
                    'filename': output_filename,
                    'object_name': object_name,
                    'download_url': _make_download_url(attachment.id),
                    'error': str(e),
                    'error_type': error_type,
                })
                if completed_counter:
                    with completed_counter['lock']:
                        completed_counter['count'] += 1
                raise

            except SFAPIError as e:
                logger.error(f"API error downloading {attachment.id}: {e}")
                stats.failed += 1
                stats.completed += 1
                err_entry = {
                    'id': attachment.id,
                    'parent_id': attachment.parent_id,
                    'name': attachment.name,
                    'error': str(e),
                    'error_type': 'SFAPIError',
                    'output_filename': output_filename,
                }
                stats.errors.append(err_entry)
                _append_to_report({
                    'attachment_id': attachment.id,
                    'parent_id': attachment.parent_id,
                    'filename': output_filename,
                    'object_name': object_name,
                    'download_url': _make_download_url(attachment.id),
                    'error': str(e),
                    'error_type': 'SFAPIError',
                })
                if completed_counter:
                    with completed_counter['lock']:
                        completed_counter['count'] += 1

            except OSError as e:
                logger.warning(
                    f"OS error for attachment {attachment.id} "
                    f"('{attachment.name}'): {e} — skipping file"
                )
                stats.failed += 1
                stats.completed += 1
                err_entry = {
                    'id': attachment.id,
                    'parent_id': attachment.parent_id,
                    'name': attachment.name,
                    'error': str(e),
                    'error_type': 'OSError',
                    'output_filename': output_filename,
                }
                stats.errors.append(err_entry)
                _append_to_report({
                    'attachment_id': attachment.id,
                    'parent_id': attachment.parent_id,
                    'filename': output_filename,
                    'object_name': object_name,
                    'download_url': _make_download_url(attachment.id),
                    'error': str(e),
                    'error_type': 'OSError',
                })
                if completed_counter:
                    with completed_counter['lock']:
                        completed_counter['count'] += 1

    finally:
        connection_pool.return_connection(sf_client)
        if worker_tracker and task_id:
            worker_tracker.unregister_task(task_id)

    logger.info(
        f"Batch complete: {stats.success} downloaded, {stats.failed} failed"
    )

    result = stats.to_dict()
    result['downloaded_entries'] = downloaded_entries
    return result
