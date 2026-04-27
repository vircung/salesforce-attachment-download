"""
Query Coordinator Module

Orchestrates Phase 2: SOQL batch query execution.
Executes batch queries for all CSVs and returns in-memory results.
"""

import logging
from pathlib import Path
from typing import List, Optional
from datetime import datetime
from threading import Lock

from src.models import CsvRecordInfo
from src.models import BatchResult, ObjectQueryResult
from src.progress.stages import SoqlQueryStage
from src.workflows.thread_pool import WorkflowThreadPool
from src.api.sf_connection import SalesforceConnectionPool
from src.api.sf_error_handler import SalesforceErrorHandler
from src.api.usage_monitor import SalesforceUsageMonitor
from src.exceptions import SFQueryError
from src.workflows.common import ensure_directories
from src.query.filters import ParentIdFilter, build_soql_where_clause
from src.query.soql_simple import query_attachments_with_simple_salesforce
from src.progress.worker_tracker import WorkerActivityTracker

logger = logging.getLogger(__name__)


def execute_all_csv_queries(
    csv_records: List[CsvRecordInfo],
    org_alias: str,
    output_dir: Path,
    soql_stage: SoqlQueryStage,
    thread_pool: WorkflowThreadPool,
    connection_pool: SalesforceConnectionPool,
    error_handler: SalesforceErrorHandler,
    usage_monitor: SalesforceUsageMonitor,
    save_metadata: bool = False,
    *,
    worker_tracker: Optional[WorkerActivityTracker] = None,
) -> List[ObjectQueryResult]:
    """
    Execute queries for ALL CSVs using threading.

    Returns in-memory ObjectQueryResult list. No intermediate CSV files
    unless save_metadata=True.

    Args:
        csv_records: List of all CSVs to query (from Phase 1)
        org_alias: Salesforce org for authentication
        output_dir: Base output directory
        soql_stage: Progress stage for batch queries
        thread_pool: Thread pool for execution
        connection_pool: SF connection pool
        error_handler: Error handler for retry logic
        usage_monitor: API usage monitor
        save_metadata: If True, write batch CSVs to disk
        worker_tracker: Optional worker activity tracker

    Returns:
        List[ObjectQueryResult] in same order as csv_records
    """
    # Calculate total batches across all CSVs
    total_batches_all_csvs = sum(csv_info.total_batches for csv_info in csv_records)

    # Start SOQL stage with total batch count
    soql_stage.start_querying(total_batches_all_csvs)

    if total_batches_all_csvs == 0:
        logger.warning("No batches to query")
        soql_stage.complete("No batches to query")
        return []

    logger.debug(f"Using threaded execution with {thread_pool.config.query_workers} workers")
    return execute_all_batches_threaded(
        csv_records=csv_records,
        org_alias=org_alias,
        output_dir=output_dir,
        soql_stage=soql_stage,
        thread_pool=thread_pool,
        connection_pool=connection_pool,
        error_handler=error_handler,
        usage_monitor=usage_monitor,
        save_metadata=save_metadata,
        worker_tracker=worker_tracker,
    )


def execute_all_batches_threaded(
    csv_records: List[CsvRecordInfo],
    org_alias: str,
    output_dir: Path,
    soql_stage: SoqlQueryStage,
    thread_pool: WorkflowThreadPool,
    connection_pool: SalesforceConnectionPool,
    error_handler: SalesforceErrorHandler,
    usage_monitor: SalesforceUsageMonitor,
    save_metadata: bool = False,
    *,
    worker_tracker: Optional[WorkerActivityTracker] = None,
) -> List[ObjectQueryResult]:
    """
    Execute all batch queries for ALL CSVs using threading.

    All batches from all CSVs are submitted to the thread pool simultaneously.
    Results are collected in memory as BatchResult instances.
    """
    # Create metadata directories upfront only when save_metadata=True
    csv_metadata_dirs = {}
    if save_metadata:
        for csv_info in csv_records:
            csv_metadata_dir = output_dir / csv_info.csv_name / 'metadata'
            ensure_directories(csv_metadata_dir)
            csv_metadata_dirs[csv_info.csv_name] = csv_metadata_dir

    # Shared counter for progress tracking
    completed_counter = {
        'count': 0,
        'total_attachments': 0,
        'lock': Lock()
    }

    # Submit all batches from all CSVs
    cumulative_batch_num = 0
    for csv_info in csv_records:
        metadata_output_dir = csv_metadata_dirs.get(csv_info.csv_name)
        for batch_idx, id_batch in enumerate(csv_info.id_batches):
            task_id = f"batch_{csv_info.csv_name}_{batch_idx}"
            logger.debug(f"Submitting task {task_id}")
            thread_pool.submit_task(
                task_id=task_id,
                fn=_execute_single_batch,
                args=(
                    task_id,
                    csv_info,
                    batch_idx,
                    id_batch,
                    org_alias,
                    metadata_output_dir,
                    cumulative_batch_num + batch_idx + 1,
                    soql_stage,
                    completed_counter,
                    connection_pool,
                    error_handler,
                    usage_monitor,
                    save_metadata,
                    worker_tracker,
                )
            )
        cumulative_batch_num += csv_info.total_batches

    logger.info(f"Submitting {cumulative_batch_num} query batches across {len(csv_records)} CSV files")

    # Wait for all tasks to complete
    worker_results = thread_pool.wait_for_completion("SOQL Query Phase", timeout=thread_pool.config.query_timeout)

    # Check for failures
    failed_tasks = [wr for wr in worker_results if not wr.success]
    if failed_tasks:
        error_messages = []
        for wr in failed_tasks:
            error_messages.append(f"Task {wr.task_id}: {wr.error} (attempts: {wr.attempts})")
        aggregated_error = "\n".join(error_messages)
        logger.error(f"Threaded query execution failed:\n{aggregated_error}")
        soql_stage.fail(f"Query execution failed: {len(failed_tasks)} tasks failed")
        raise SFQueryError(f"Query execution failed: {aggregated_error}")

    # Organize BatchResults by CSV name
    csv_batches: dict[str, list[BatchResult]] = {csv_info.csv_name: [] for csv_info in csv_records}
    for wr in worker_results:
        if wr.success and isinstance(wr.result, tuple):
            csv_name, batch_result = wr.result
            csv_batches[csv_name].append(batch_result)

    # Build ObjectQueryResult list
    object_results = []
    total_attachments = 0
    for csv_info in csv_records:
        batches = csv_batches[csv_info.csv_name]
        obj_result = ObjectQueryResult(
            csv_name=csv_info.csv_name,
            batches=batches,
        )
        total_attachments += obj_result.total_attachments
        logger.info(f"{csv_info.csv_name}: {len(batches)} batch(es), {obj_result.total_attachments} attachment(s)")
        object_results.append(obj_result)

    # Complete SOQL stage
    total_batches = sum(len(csv_batches[csv.csv_name]) for csv in csv_records)
    soql_stage.complete(f"Completed {total_batches} batches, found {completed_counter['total_attachments']} attachments")

    logger.info(f"Threaded query execution completed: {total_batches} batches, {total_attachments} attachments")

    return object_results


def _execute_single_batch(
    batch_id: str,
    csv_info: CsvRecordInfo,
    batch_idx: int,
    id_batch: List[str],
    org_alias: str,
    metadata_output_dir: Optional[Path],
    cumulative_batch_num: int,
    soql_stage: SoqlQueryStage,
    completed_counter: dict,
    connection_pool: SalesforceConnectionPool,
    error_handler: SalesforceErrorHandler,
    usage_monitor: SalesforceUsageMonitor,
    save_metadata: bool = False,
    worker_tracker: Optional[WorkerActivityTracker] = None,
) -> tuple:
    """
    Execute a single batch query in a worker thread.

    Returns:
        Tuple of (csv_name, BatchResult)
    """
    if worker_tracker:
        worker_tracker.register_task(
            batch_id, "SOQL", csv_info.csv_name, batch_idx, len(id_batch)
        )

    try:
        logger.debug(f"Executing batch {batch_id}: {len(id_batch)} ParentId(s)")

        if worker_tracker:
            worker_tracker.update_task(batch_id, 0, "querying...")

        # Update progress before query execution
        soql_stage.update_batch(
            completed_batches=completed_counter['count'],
            current_batch=cumulative_batch_num,
            batch_size=len(id_batch)
        )

        # Build WHERE clause
        filter_config = ParentIdFilter(
            prefixes=[],
            exact_ids=id_batch,
            strategy='soql'
        )
        where_clause = build_soql_where_clause(filter_config)

        # Construct metadata CSV path when save_metadata=True
        metadata_csv_path = None
        if save_metadata and metadata_output_dir:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            metadata_csv_path = metadata_output_dir / f"batch_{batch_idx}_{timestamp}.csv"

        # Execute query — returns List[AttachmentRecord]
        attachment_records = query_attachments_with_simple_salesforce(
            org_alias=org_alias,
            where_clause=where_clause,
            connection_pool=connection_pool,
            error_handler=error_handler,
            usage_monitor=usage_monitor,
            save_metadata=save_metadata,
            metadata_csv_path=metadata_csv_path,
        )

        attachment_count = len(attachment_records)

        if worker_tracker:
            worker_tracker.update_task(
                batch_id, attachment_count, f"done, {attachment_count} found"
            )

        with completed_counter['lock']:
            completed_counter['count'] += 1
            completed_counter['total_attachments'] += attachment_count
            snapshot_total = completed_counter['total_attachments']

        soql_stage.complete_batch(
            batch_num=cumulative_batch_num,
            records_found=attachment_count,
            total_attachments=snapshot_total
        )

        logger.info(f"Batch {batch_id} completed: {attachment_count} attachment(s)")

        batch_result = BatchResult(
            batch_idx=batch_idx,
            attachments=attachment_records,
        )

        return (csv_info.csv_name, batch_result)

    finally:
        if worker_tracker:
            worker_tracker.unregister_task(batch_id)
