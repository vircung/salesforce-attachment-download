"""
Download Coordinator Module

Orchestrates Phase 3: File download execution.
Objects processed sequentially, batches within each object in parallel.
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple, Set
from dataclasses import dataclass
from threading import Lock

from src.models import AttachmentRecord, BatchResult, ObjectQueryResult
from src.progress.stages import DownloadStage
from src.workflows.thread_pool import WorkflowThreadPool
from src.workflows.common import ensure_directories
from src.api.sf_connection import SalesforceConnectionPool
from src.api.sf_error_handler import SalesforceErrorHandler
from src.api.usage_monitor import SalesforceUsageMonitor
from src.download.filename import (
    detect_filename_collisions, build_output_filename, FilenameInfo
)
from src.download.scan import (
    scan_existing_files, load_skipped_attachment_ids, write_skipped_files_report
)

logger = logging.getLogger(__name__)


@dataclass
class DownloadResult:
    """Result of downloading attachments for a single object."""
    csv_name: str
    downloaded_count: int
    skipped_count: int
    failed_count: int
    errors: List[Dict[str, Any]]
    total_attachments: int


def split_batches(
    batches: List[BatchResult],
    filename_info_map: Dict[str, FilenameInfo],
    existing_filenames: Set[str],
    skipped_ids: Set[str],
) -> Tuple[List[BatchResult], int, int]:
    """Split batches into to_download and already_exists.

    For each attachment in each batch:
    - build output filename via build_output_filename()
    - if filename in existing_filenames -> skip (already downloaded)
    - if attachment.id in skipped_ids -> skip (permanently failed)
    - otherwise -> include in to_download

    Returns:
        (to_download_batches, skipped_existing_count, skipped_permanent_count)

    Preserves original batch_idx. Excludes empty batches.
    """
    to_download_batches = []
    skipped_existing = 0
    skipped_permanent = 0

    for batch in batches:
        remaining = []
        for attachment in batch.attachments:
            if attachment.id in skipped_ids:
                skipped_permanent += 1
                continue
            output_filename = build_output_filename(attachment, filename_info_map)
            if output_filename in existing_filenames:
                skipped_existing += 1
                continue
            remaining.append(attachment)

        if remaining:
            to_download_batches.append(BatchResult(
                batch_idx=batch.batch_idx,
                attachments=remaining,
            ))

    return to_download_batches, skipped_existing, skipped_permanent


def coordinate_all_downloads(
    object_results: List[ObjectQueryResult],
    org_alias: str,
    output_dir: Path,
    download_stage: DownloadStage,
    thread_pool: WorkflowThreadPool,
    connection_pool: SalesforceConnectionPool,
    error_handler: SalesforceErrorHandler,
    usage_monitor: SalesforceUsageMonitor,
    download_enabled: bool = True,
) -> List[DownloadResult]:
    """
    Coordinate download of all attachments.

    Objects processed sequentially, batches within each object in parallel.
    """
    if not download_enabled:
        return [
            DownloadResult(
                csv_name=obj.csv_name, downloaded_count=0,
                skipped_count=0, failed_count=0, errors=[],
                total_attachments=obj.total_attachments
            )
            for obj in object_results
        ]

    # Compute total across all objects
    total_all = sum(obj.total_attachments for obj in object_results)
    download_stage.start_downloads(total_all)

    # One completed_counter for the entire run (cumulative, not reset per object)
    completed_counter = {'count': 0, 'lock': Lock()}

    # instance_url for skipped_files.json manual download URLs
    instance_url = connection_pool.instance_url

    all_download_results = []

    # Lazy import to avoid circular dependency
    from src.download.downloader_simple import download_batch

    for obj_result in object_results:
        output_files_dir = output_dir / obj_result.csv_name / 'files'
        ensure_directories(output_files_dir)

        # Flatten for collision detection
        all_attachments = [a for b in obj_result.batches for a in b.attachments]
        filename_info_map = detect_filename_collisions(all_attachments)

        # Scan + split
        existing = scan_existing_files(output_files_dir)
        skipped_files_path = output_dir / 'skipped_files.json'
        skipped_ids = load_skipped_attachment_ids(skipped_files_path)

        to_download_batches, skipped_existing, skipped_permanent = split_batches(
            obj_result.batches, filename_info_map, existing, skipped_ids
        )

        total_skipped = skipped_existing + skipped_permanent
        if total_skipped > 0:
            download_stage.adjust_total(total_skipped)

        # Submit per-batch workers
        for batch in to_download_batches:
            thread_pool.submit_task(
                task_id=f"download_{obj_result.csv_name}_batch_{batch.batch_idx}",
                fn=download_batch,
                max_retries=1,
                args=(
                    batch.attachments, output_files_dir, filename_info_map,
                    connection_pool, error_handler, usage_monitor,
                    download_stage, completed_counter
                )
            )

        # Wait for this object's batches (no timeout for downloads)
        worker_results = thread_pool.wait_for_completion(
            phase_name=f"download_{obj_result.csv_name}",
            timeout=None
        )
        thread_pool.clear_results()

        # Aggregate batch results into DownloadResult
        total_downloaded = 0
        total_failed = 0
        all_errors: List[Dict[str, Any]] = []

        # Exact-match lookup: task_id -> batch
        batch_by_task = {
            f"download_{obj_result.csv_name}_batch_{b.batch_idx}": b
            for b in to_download_batches
        }

        for wr in worker_results:
            if wr.success and wr.result:
                total_downloaded += wr.result['success']
                total_failed += wr.result['failed']
                all_errors.extend(wr.result.get('errors', []))
            elif not wr.success:
                # Failed worker (e.g. SFNetworkError/SFAuthError)
                batch = batch_by_task.get(wr.task_id)
                batch_size = len(batch.attachments) if batch else 0
                total_failed += batch_size
                logger.error(f"Batch worker {wr.task_id} failed: {wr.error}")

        # Write skipped_files.json for OS errors
        os_errors = [e for e in all_errors if e.get('error_type') == 'OSError']
        if os_errors:
            write_skipped_files_report(os_errors, skipped_files_path, instance_url)

        all_download_results.append(DownloadResult(
            csv_name=obj_result.csv_name,
            downloaded_count=total_downloaded,
            skipped_count=total_skipped,
            failed_count=total_failed,
            errors=all_errors,
            total_attachments=obj_result.total_attachments,
        ))

    # Mark download phase complete
    total_dl = sum(dr.downloaded_count for dr in all_download_results)
    total_fail = sum(dr.failed_count for dr in all_download_results)
    total_skip = sum(dr.skipped_count for dr in all_download_results)
    download_stage.complete(
        f"Downloaded {total_dl} files, failed {total_fail}, skipped {total_skip}"
    )

    return all_download_results
