"""
Download Coordinator Module

Orchestrates Phase 3: File download execution.
Two-pass architecture:
  Pass 1 (prep): scan, collision detection, split for all objects
  Pass 2 (download): submit batch workers per object, wait per object
"""

import logging
import shutil
from pathlib import Path
from typing import List, Dict, Any, Tuple, Set, Optional
from dataclasses import dataclass, field
from threading import Lock

from src.models import AttachmentRecord, BatchResult, ObjectQueryResult
from src.progress.stages import DownloadStage
from src.progress.stages.download_prep_stage import DownloadPrepStage
from src.workflows.thread_pool import WorkflowThreadPool
from src.workflows.common import ensure_directories
from src.api.sf_connection import SalesforceConnectionPool
from src.api.sf_error_handler import SalesforceErrorHandler
from src.api.usage_monitor import SalesforceUsageMonitor
from src.download.filename import (
    detect_filename_collisions, build_output_filename, FilenameInfo
)
from src.download.downloader_simple import make_download_url
from src.download.scan import scan_existing_files, load_skipped_attachment_ids
from src.report.writer import REPORT_MISSING
from src.progress.worker_tracker import WorkerActivityTracker

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
    downloaded_entries: List[Dict[str, Any]] = field(default_factory=list)
    error_entries: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ObjectPrepResult:
    """Intermediate structure carrying prep results between Pass 1 and Pass 2."""
    obj_result: ObjectQueryResult
    to_download_batches: List[BatchResult]
    filename_info_map: Dict[str, FilenameInfo]
    output_obj_dir: Path
    skipped_existing: int
    skipped_permanent: int


def split_batches(
    batches: List[BatchResult],
    filename_info_map: Dict[str, FilenameInfo],
    existing_filenames: Set[str],
    skipped_ids: Set[str],
) -> Tuple[List[BatchResult], int, int]:
    """Split batches into to_download and already_exists.

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


def _cleanup_obj_dir(output_obj_dir: Path) -> None:
    """Remove temp dirs and empty object directories after download."""
    try:
        if not output_obj_dir.exists():
            return

        # Always clean .tmp_downloads
        tmp_dir = output_obj_dir / '.tmp_downloads'
        if tmp_dir.exists():
            try:
                shutil.rmtree(tmp_dir)
            except OSError as e:
                logger.warning("Could not remove %s: %s", tmp_dir, e)

        # Check if dir has any real files (not just subdirs)
        has_flat_files = any(e.is_file() for e in output_obj_dir.iterdir())
        legacy_dir = output_obj_dir / 'files'
        has_legacy_files = (
            legacy_dir.is_dir()
            and any(e.is_file() for e in legacy_dir.iterdir())
        )
        has_files = has_flat_files or has_legacy_files

        if not has_files:
            # No downloaded files anywhere — clean up empty subdirs
            for subdir_name in ('metadata', 'files'):
                subdir = output_obj_dir / subdir_name
                if subdir.exists() and not any(subdir.iterdir()):
                    try:
                        subdir.rmdir()
                    except OSError as e:
                        logger.warning("Could not remove %s: %s", subdir, e)

        # Remove object dir if now empty
        if not any(output_obj_dir.iterdir()):
            output_obj_dir.rmdir()

    except OSError as e:
        logger.debug("Cleanup failed for %s: %s", output_obj_dir, e)


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
    *,
    download_prep_stage: Optional[DownloadPrepStage] = None,
    worker_tracker: Optional[WorkerActivityTracker] = None,
) -> List[DownloadResult]:
    """
    Coordinate download of all attachments.

    Two-pass architecture:
      Pass 1: scan + collision detection + split for all objects
      Pass 2: submit batch workers per object, wait per object
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

    # Clear stale results from query phase
    thread_pool.clear_results()

    # Clear worker tracker from SOQL phase
    if worker_tracker:
        worker_tracker.clear_all_tasks()

    # Hoist shared state
    report_missing_path = output_dir / REPORT_MISSING

    # ================================================================
    # PASS 1: PREP — scan, collision detection, split for all objects
    # ================================================================
    total_to_download = 0
    total_skipped = 0
    prep_results: List[ObjectPrepResult] = []

    if download_prep_stage:
        download_prep_stage.start_prep(len(object_results))

    try:
        for i, obj_result in enumerate(object_results):
            output_obj_dir = output_dir / obj_result.csv_name

            # Flatten for collision detection
            all_attachments = [a for b in obj_result.batches for a in b.attachments]
            filename_info_map = detect_filename_collisions(all_attachments)

            # Scan existing + load skipped IDs (per-object read)
            existing = scan_existing_files(output_obj_dir)
            skipped_ids = load_skipped_attachment_ids(report_missing_path)

            to_download_batches, skipped_existing, skipped_permanent = split_batches(
                obj_result.batches, filename_info_map, existing, skipped_ids
            )

            obj_to_download = sum(len(b.attachments) for b in to_download_batches)
            obj_skipped = skipped_existing + skipped_permanent
            total_to_download += obj_to_download
            total_skipped += obj_skipped

            # Only create directory when there are files to download
            if obj_to_download > 0:
                ensure_directories(output_obj_dir)

            prep_results.append(ObjectPrepResult(
                obj_result=obj_result,
                to_download_batches=to_download_batches,
                filename_info_map=filename_info_map,
                output_obj_dir=output_obj_dir,
                skipped_existing=skipped_existing,
                skipped_permanent=skipped_permanent,
            ))

            if download_prep_stage:
                download_prep_stage.update_object(
                    object_idx=i + 1,
                    object_name=obj_result.csv_name,
                    to_download=obj_to_download,
                    skipped=obj_skipped,
                )

        if download_prep_stage:
            download_prep_stage.complete_prep(total_to_download, total_skipped)

    except Exception:
        if download_prep_stage:
            download_prep_stage.fail("Download preparation failed")
        raise

    # ================================================================
    # BETWEEN PASSES: start download stage with exact total
    # ================================================================
    download_stage.start_downloads(total_to_download)

    # ================================================================
    # PASS 2: DOWNLOAD — submit batch workers per object, wait per object
    # ================================================================
    completed_counter = {'count': 0, 'lock': Lock()}
    instance_url = connection_pool.instance_url

    # Lazy import inside function to avoid circular dependency
    from src.download.downloader_simple import download_batch

    all_download_results = []

    for prep in prep_results:
        obj_result = prep.obj_result

        # Shared report entries container for fatal error preservation
        report_entries: Dict[str, Any] = {'entries': [], 'lock': Lock()}

        # Submit per-batch workers
        for batch in prep.to_download_batches:
            dl_task_id = f"download_{obj_result.csv_name}_batch_{batch.batch_idx}"
            thread_pool.submit_task(
                task_id=dl_task_id,
                fn=download_batch,
                max_retries=1,
                args=(
                    batch.attachments, prep.output_obj_dir, prep.filename_info_map,
                    connection_pool, error_handler, usage_monitor,
                    download_stage, completed_counter,
                    worker_tracker, dl_task_id, obj_result.csv_name, batch.batch_idx,
                    report_entries, instance_url,
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
        obj_downloaded_entries: List[Dict[str, Any]] = []
        obj_error_entries: List[Dict[str, Any]] = []

        # Exact-match lookup: task_id -> batch
        batch_by_task = {
            f"download_{obj_result.csv_name}_batch_{b.batch_idx}": b
            for b in prep.to_download_batches
        }

        for wr in worker_results:
            if wr.success and wr.result:
                # Successful batch — use wr.result data
                total_downloaded += wr.result['success']
                total_failed += wr.result['failed']
                all_errors.extend(wr.result.get('errors', []))
                obj_downloaded_entries.extend(wr.result.get('downloaded_entries', []))

                # Build error entries from normalized error dicts
                for err in wr.result.get('errors', []):
                    obj_error_entries.append({
                        'attachment_id': err.get('id', ''),
                        'parent_id': err.get('parent_id', ''),
                        'filename': err.get('output_filename', err.get('name', '')),
                        'object_name': obj_result.csv_name,
                        'download_url': make_download_url(instance_url, err.get('id', '')),
                        'error': err.get('error', ''),
                        'error_type': err.get('error_type', 'Unknown'),
                    })

            elif not wr.success:
                # Failed batch — wr.result is None, use report_entries
                batch = batch_by_task.get(wr.task_id)
                if not batch:
                    logger.error(f"Batch worker {wr.task_id} failed: {wr.error}")
                    continue

                batch_attachment_ids = {a.id for a in batch.attachments}
                batch_size = len(batch.attachments)
                total_failed += batch_size
                logger.error(f"Batch worker {wr.task_id} failed: {wr.error}")

                # Filter report_entries to this batch's attachments only
                batch_report = [
                    e for e in report_entries['entries']
                    if e.get('attachment_id') in batch_attachment_ids
                ]

                # Separate downloaded vs error entries from shared container
                processed_ids = set()
                for entry in batch_report:
                    processed_ids.add(entry['attachment_id'])
                    if entry.get('error'):
                        obj_error_entries.append(entry)
                    else:
                        obj_downloaded_entries.append(entry)
                        total_downloaded += 1
                        total_failed -= 1  # Adjust: was counted as failed above

                # Create BatchAborted entries for unprocessed attachments
                for attachment in batch.attachments:
                    if attachment.id not in processed_ids:
                        output_filename = build_output_filename(
                            attachment, prep.filename_info_map
                        )
                        obj_error_entries.append({
                            'attachment_id': attachment.id,
                            'parent_id': attachment.parent_id,
                            'filename': output_filename,
                            'object_name': obj_result.csv_name,
                            'download_url': make_download_url(instance_url, attachment.id),
                            'error': 'Batch aborted due to fatal error',
                            'error_type': 'BatchAborted',
                        })

        obj_skipped = prep.skipped_existing + prep.skipped_permanent
        all_download_results.append(DownloadResult(
            csv_name=obj_result.csv_name,
            downloaded_count=total_downloaded,
            skipped_count=obj_skipped,
            failed_count=max(0, total_failed),
            errors=all_errors,
            total_attachments=obj_result.total_attachments,
            downloaded_entries=obj_downloaded_entries,
            error_entries=obj_error_entries,
        ))

        # Cleanup after everything is done for this object
        _cleanup_obj_dir(prep.output_obj_dir)

    # Mark download phase complete
    total_dl = sum(dr.downloaded_count for dr in all_download_results)
    total_fail = sum(dr.failed_count for dr in all_download_results)
    total_skip = sum(dr.skipped_count for dr in all_download_results)
    download_stage.complete(
        f"Downloaded {total_dl} files, failed {total_fail}, skipped {total_skip}"
    )

    return all_download_results
