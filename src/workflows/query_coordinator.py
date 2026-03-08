"""
Query Coordinator Module

Orchestrates Phase 2: SOQL batch query execution.
Executes batch queries for all CSVs and consolidates results.
Results are merged per CSV file (not globally).
"""

import csv
import logging
from pathlib import Path
from typing import List
from dataclasses import dataclass
from datetime import datetime
from threading import Lock

from src.constants import CsvRecordInfo
from src.progress.stages import SoqlQueryStage
from src.workflows.thread_pool import WorkflowThreadPool
from src.api.sf_connection import SalesforceConnectionPool
from src.api.sf_error_handler import SalesforceErrorHandler
from src.api.usage_monitor import SalesforceUsageMonitor
from src.exceptions import SFQueryError
from src.workflows.common import ensure_directories, merge_csv_files
from src.query.filters import ParentIdFilter, build_soql_where_clause
from src.query.soql_simple import query_attachments_with_simple_salesforce

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    """Result of querying attachments for a single CSV."""
    csv_name: str
    batch_csv_paths: List[Path]  # Individual batch result files
    merged_csv_path: Path  # All batches merged into one per-CSV file
    total_attachments_found: int
    cumulative_batches_completed: int  # For tracking progress across all CSVs


@dataclass
class QueryBatchResult:
    """Result of a single batch query execution."""
    csv_name: str
    batch_idx: int
    batch_csv_path: Path
    attachment_count: int
    batch_size: int
    cumulative_batch_num: int


def execute_all_csv_queries(
    csv_records: List[CsvRecordInfo],
    org_alias: str,
    output_dir: Path,
    soql_stage: SoqlQueryStage,
    thread_pool: WorkflowThreadPool,
    connection_pool: SalesforceConnectionPool,
    error_handler: SalesforceErrorHandler,
    usage_monitor: SalesforceUsageMonitor
) -> List[QueryResult]:
    """
    Execute queries for ALL CSVs sequentially.
    
    This is PHASE 2: For each CSV, execute all batch queries and merge results.
    Queries complete for all CSVs before Phase 3 (downloads) begins.
    
    Process:
      1. Calculate total_batches across all CSVs
      2. Start SOQL stage with total batch count
      3. For each CSV in csv_records:
         - Create per-CSV metadata directory
         - Call execute_csv_batch_queries()
         - Accumulate cumulative batch count
      4. Return list of QueryResult (one per CSV, in same order)
    
    Args:
        csv_records: List of all CSVs to query (from Phase 1)
        org_alias: Salesforce org for authentication
        output_dir: Base output directory (will create {csv_name}/metadata/ subdirs)
        soql_stage: Progress stage for batch queries
        thread_pool: Thread pool for execution
    
    Returns:
        List[QueryResult] in same order as csv_records
    
    Raises:
        SFQueryError: If any batch query fails (entire Phase 2 fails)
        SFAuthError: If auth fails (entire Phase 2 fails)
        SFAPIError: If API error occurs (entire Phase 2 fails)
    """
    # Calculate total batches across all CSVs
    total_batches_all_csvs = sum(csv_info.total_batches for csv_info in csv_records)
    
    # Start SOQL stage with total batch count
    soql_stage.start_querying(total_batches_all_csvs)
    
    if total_batches_all_csvs == 0:
        logger.warning("No batches to query")
        soql_stage.complete("No batches to query")
        return []
    
    # Determine execution mode
    logger.debug(f"Using threaded execution with {thread_pool.config.query_workers} workers")
    return execute_all_batches_threaded(
        csv_records=csv_records,
        org_alias=org_alias,
        output_dir=output_dir,
        soql_stage=soql_stage,
        thread_pool=thread_pool,
        connection_pool=connection_pool,
        error_handler=error_handler,
        usage_monitor=usage_monitor
    )


def execute_all_batches_threaded(
    csv_records: List[CsvRecordInfo],
    org_alias: str,
    output_dir: Path,
    soql_stage: SoqlQueryStage,
    thread_pool: WorkflowThreadPool,
    connection_pool: SalesforceConnectionPool,
    error_handler: SalesforceErrorHandler,
    usage_monitor: SalesforceUsageMonitor
) -> List[QueryResult]:
    """
    Execute all batch queries for ALL CSVs using threading.
    
    Process:
      1. Calculate total_batches across all CSVs
      2. Create metadata directories for all CSVs upfront
      3. Submit all batches from all CSVs to thread_pool
      4. Wait for all tasks to complete
      5. Collect results and organize by CSV
      6. Merge batches per CSV
      7. Return list of QueryResult
    
    Args:
        csv_records: List of all CSVs to query (from Phase 1)
        org_alias: Salesforce org for authentication
        output_dir: Base output directory (will create {csv_name}/metadata/ subdirs)
        soql_stage: Progress stage for batch queries
        thread_pool: Thread pool for parallel execution
    
    Returns:
        List[QueryResult] in same order as csv_records
    
    Raises:
        SFQueryError: If any batch query fails after retries
        SFAuthError: If auth fails
        SFAPIError: If API error occurs
    """
    # Create metadata directories for all CSVs upfront
    csv_metadata_dirs = {}
    for csv_info in csv_records:
        csv_metadata_dir = output_dir / csv_info.csv_name / 'metadata'
        ensure_directories(csv_metadata_dir)
        csv_metadata_dirs[csv_info.csv_name] = csv_metadata_dir
    
    # Create shared counter for progress tracking
    completed_counter = {
        'count': 0,
        'total_attachments': 0,
        'lock': Lock()
    }
    
    # Submit all batches from all CSVs
    cumulative_batch_num = 0
    for csv_info in csv_records:
        metadata_output_dir = csv_metadata_dirs[csv_info.csv_name]
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
                    usage_monitor
                )
            )
        cumulative_batch_num += csv_info.total_batches
    
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
    
    # Organize results by CSV
    csv_results = {csv_info.csv_name: [] for csv_info in csv_records}
    for wr in worker_results:
        if wr.success and isinstance(wr.result, QueryBatchResult):
            csv_results[wr.result.csv_name].append(wr.result)
    
    # Merge batches per CSV and create QueryResult
    query_results = []
    total_attachments = 0
    for csv_info in csv_records:
        batch_results = csv_results[csv_info.csv_name]
        batch_csv_paths = [qbr.batch_csv_path for qbr in batch_results]
        
        # Merge batch CSVs
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        merged_csv_path = csv_metadata_dirs[csv_info.csv_name] / f"attachments_{timestamp}_merged.csv"
        merged_count = merge_csv_files(batch_csv_paths, merged_csv_path)
        total_attachments += merged_count
        
        logger.info(f"Merged {len(batch_csv_paths)} batch(es) for {csv_info.csv_name}: {merged_count} attachment(s)")
        
        query_result = QueryResult(
            csv_name=csv_info.csv_name,
            batch_csv_paths=batch_csv_paths,
            merged_csv_path=merged_csv_path,
            total_attachments_found=merged_count,
            cumulative_batches_completed=sum(len(csv_results[csv.csv_name]) for csv in csv_records[:csv_records.index(csv_info) + 1])
        )
        query_results.append(query_result)
    
    # Complete SOQL stage
    total_batches = sum(len(csv_results[csv.csv_name]) for csv in csv_records)
    soql_stage.complete(f"Completed {total_batches} batches, found {completed_counter['total_attachments']} attachments")
    
    logger.info(f"Threaded query execution completed: {total_batches} batches, {total_attachments} attachments")
    
    return query_results


def _execute_single_batch(
    batch_id: str,
    csv_info: CsvRecordInfo,
    batch_idx: int,
    id_batch: List[str],
    org_alias: str,
    metadata_output_dir: Path,
    cumulative_batch_num: int,
    soql_stage: SoqlQueryStage,
    completed_counter: dict,
    connection_pool: SalesforceConnectionPool,
    error_handler: SalesforceErrorHandler,
    usage_monitor: SalesforceUsageMonitor
) -> QueryBatchResult:
    """
    Execute a single batch query in a worker thread.
    
    Args:
        batch_id: Task identifier (e.g., "batch_contacts.csv_0")
        csv_info: CSV information
        batch_idx: Batch index within the CSV
        id_batch: List of ParentId values for this batch
        org_alias: Salesforce org alias
        metadata_output_dir: Directory to store batch CSV
        cumulative_batch_num: Global batch number across all CSVs
    
    Returns:
        QueryBatchResult with batch details
    
    Raises:
        Exception: If query fails (will be retried by thread_pool)
    """
    logger.debug(f"Executing batch {batch_id}: {len(id_batch)} ParentId(s)")
    
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
    
    # Execute query using simple-salesforce
    batch_csv_path = query_attachments_with_simple_salesforce(
        org_alias=org_alias,
        output_dir=metadata_output_dir,
        where_clause=where_clause,
        connection_pool=connection_pool,
        error_handler=error_handler,
        usage_monitor=usage_monitor
    )
    
    # Count results
    with batch_csv_path.open('r', encoding='utf-8') as f:
        attachment_count = sum(1 for _ in csv.DictReader(f))
    
    # Update counter atomically
    with completed_counter['lock']:
        completed_counter['count'] += 1
        completed_counter['total_attachments'] += attachment_count
    
    # Complete batch
    soql_stage.complete_batch(
        batch_num=cumulative_batch_num,
        records_found=attachment_count,
        total_attachments=completed_counter['total_attachments']
    )
    
    logger.info(f"Batch {batch_id} completed: {attachment_count} attachment(s)")
    
    return QueryBatchResult(
        csv_name=csv_info.csv_name,
        batch_idx=batch_idx,
        batch_csv_path=batch_csv_path,
        attachment_count=attachment_count,
        batch_size=len(id_batch),
        cumulative_batch_num=cumulative_batch_num
    )