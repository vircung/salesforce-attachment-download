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

from src.csv.processor import CsvRecordInfo
from src.query.executor import run_query_script_with_filter
from src.query.filters import ParentIdFilter, build_soql_where_clause
from src.workflows.common import merge_csv_files
from src.progress.stages import SoqlQueryStage
from src.utils import log_section_header
from src.exceptions import SFQueryError, SFAuthError, SFAPIError

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    """Result of querying attachments for a single CSV."""
    csv_name: str
    batch_csv_paths: List[Path]  # Individual batch result files
    merged_csv_path: Path  # All batches merged into one per-CSV file
    total_attachments_found: int
    cumulative_batches_completed: int  # For tracking progress across all CSVs


def execute_all_csv_queries(
    csv_records: List[CsvRecordInfo],
    org_alias: str,
    output_dir: Path,
    soql_stage: SoqlQueryStage,
    batch_size: int
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
        batch_size: Batch size (for logging)
    
    Returns:
        List[QueryResult] in same order as csv_records
    
    Raises:
        SFQueryError: If any batch query fails (entire Phase 2 fails)
        SFAuthError: If auth fails (entire Phase 2 fails)
        SFAPIError: If API error occurs (entire Phase 2 fails)
    """
    log_section_header("PHASE 2: SOQL BATCH QUERYING")
    
    # Calculate total batches across all CSVs
    total_batches_all_csvs = sum(csv_info.total_batches for csv_info in csv_records)
    
    # Start SOQL stage with total batch count
    soql_stage.start_querying(total_batches_all_csvs)
    
    if total_batches_all_csvs == 0:
        logger.warning("No batches to query")
        soql_stage.complete("No batches to query")
        return []
    
    query_results = []
    cumulative_batches_completed = 0
    
    # Process each CSV
    for csv_idx, csv_info in enumerate(csv_records, start=1):
        logger.info(f"Processing CSV {csv_idx}/{len(csv_records)}: {csv_info.csv_name}")
        logger.info(f"  Records: {csv_info.total_records}")
        logger.info(f"  Batches: {csv_info.total_batches}")
        
        # Create metadata directory for this CSV
        csv_metadata_dir = output_dir / csv_info.csv_name / 'metadata'
        csv_metadata_dir.mkdir(parents=True, exist_ok=True)
        
        # Update SOQL stage to show current CSV
        soql_stage.update_progress(
            message=f"Processing {csv_info.csv_name} ({csv_info.total_batches} batches)",
            details={
                "current_csv": csv_info.csv_name,
                "csv_batches": csv_info.total_batches,
                "csv_index": f"{csv_idx}/{len(csv_records)}"
            }
        )
        
        # Execute all batches for this CSV
        query_result = execute_csv_batch_queries(
            csv_info=csv_info,
            org_alias=org_alias,
            metadata_output_dir=csv_metadata_dir,
            soql_stage=soql_stage,
            cumulative_batches_completed=cumulative_batches_completed,
            total_batches_all_csvs=total_batches_all_csvs
        )
        
        query_results.append(query_result)
        cumulative_batches_completed += csv_info.total_batches
    
    # Complete SOQL stage
    total_attachments = sum(qr.total_attachments_found for qr in query_results)
    soql_stage.complete(
        f"Completed {total_batches_all_csvs} batches, found {total_attachments} attachments"
    )
    
    return query_results


def execute_csv_batch_queries(
    csv_info: CsvRecordInfo,
    org_alias: str,
    metadata_output_dir: Path,
    soql_stage: SoqlQueryStage,
    cumulative_batches_completed: int,
    total_batches_all_csvs: int
) -> QueryResult:
    """
    Execute all batch queries for a SINGLE CSV file.
    
    For each batch in csv_info.id_batches:
      1. Build WHERE clause with ParentId IN (...)
      2. Execute query via run_query_script_with_filter()
      3. Count attachment results
      4. Update SOQL stage progress
      5. Complete batch in stage
    
    After all batches for this CSV:
      1. Merge all batch CSVs into single metadata CSV
      2. Return QueryResult with merged CSV path
    
    Args:
        csv_info: CSV to query (contains id_batches)
        org_alias: Salesforce org for authentication
        metadata_output_dir: Where to store batch CSVs and merged CSV
        soql_stage: Progress stage for updates
        cumulative_batches_completed: Batches completed in previous CSVs
        total_batches_all_csvs: Total batches across all CSVs (for global progress)
    
    Returns:
        QueryResult with merged CSV path and attachment count
    
    Raises:
        SFQueryError: If any batch query fails
        SFAuthError: If auth fails
        SFAPIError: If API error occurs
    """
    batch_csv_paths = []
    total_attachments = 0
    
    # Execute each batch for this CSV
    for batch_idx, id_batch in enumerate(csv_info.id_batches):
        batch_num = batch_idx + 1
        total_batches = csv_info.total_batches
        id_count = len(id_batch)
        logger.info(
            f"Batch {batch_num}/{total_batches}: Querying {id_count} ParentId(s)"
        )
        
        # Update SOQL stage with cumulative batch progress
        soql_stage.update_batch(
            completed_batches=cumulative_batches_completed + batch_idx,
            current_batch=cumulative_batches_completed + batch_idx + 1,
            batch_size=len(id_batch)
        )
        
        # Build WHERE clause using ParentId IN (...)
        filter_config = ParentIdFilter(
            prefixes=[],
            exact_ids=id_batch,
            strategy='soql'
        )
        where_clause = build_soql_where_clause(filter_config)
        
        # Execute query
        batch_csv_path = run_query_script_with_filter(
            org_alias=org_alias,
            output_dir=metadata_output_dir,
            where_clause=where_clause
        )
        
        batch_csv_paths.append(batch_csv_path)
        
        # Count rows in batch (for reporting)
        with batch_csv_path.open('r', encoding='utf-8') as f:
            batch_count = sum(1 for _ in csv.DictReader(f))
            total_attachments += batch_count
            logger.info(
                f"Batch {batch_idx + 1}/{csv_info.total_batches}: "
                f"Found {batch_count} attachment(s)"
            )
        
        # Complete this batch in stage
        soql_stage.complete_batch(
            batch_num=cumulative_batches_completed + batch_idx + 1,
            records_found=batch_count,
            total_attachments=total_attachments
        )
    
    # Merge all batch CSVs for this CSV into one
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    merged_csv_path = metadata_output_dir / f"attachments_{timestamp}_merged.csv"
    
    merged_count = merge_csv_files(batch_csv_paths, merged_csv_path)
    logger.info(
        f"Merged {len(batch_csv_paths)} batch(es) into "
        f"{merged_csv_path.name}: {merged_count} attachment(s)"
    )
    
    return QueryResult(
        csv_name=csv_info.csv_name,
        batch_csv_paths=batch_csv_paths,
        merged_csv_path=merged_csv_path,
        total_attachments_found=merged_count,
        cumulative_batches_completed=cumulative_batches_completed + csv_info.total_batches
    )