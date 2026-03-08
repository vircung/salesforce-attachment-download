"""
Simple-Salesforce SOQL Query Execution Module

This module provides SOQL query execution using simple-salesforce library
instead of sf CLI subprocess calls, for better performance and error handling.
"""

import csv
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from threading import Lock

from simple_salesforce.api import Salesforce

from src.api.sf_connection import SalesforceConnectionPool
from src.api.sf_error_handler import SalesforceErrorHandler
from src.api.usage_monitor import SalesforceUsageMonitor
from src.exceptions import SFQueryError
from src.models import AttachmentRecord

logger = logging.getLogger(__name__)

# Thread-safe flag to track if query template details have been logged
_query_logged_lock = Lock()
_query_logged = False

# Salesforce Attachment fields to query
ATTACHMENT_FIELDS = [
    'Id',
    'Name',
    'ContentType',
    'BodyLength',
    'ParentId',
    'CreatedDate',
    'LastModifiedDate',
    'Description'
]


def build_attachment_query(where_clause: str) -> str:
    """
    Build SOQL query for Attachment records.

    Args:
        where_clause: WHERE clause (e.g., "WHERE ParentId IN ('id1','id2')")

    Returns:
        Complete SOQL query string

    Example:
        >>> build_attachment_query("WHERE ParentId IN ('001xxx')")
        "SELECT Id, Name, ... FROM Attachment WHERE ParentId IN ('001xxx') ORDER BY ..."
    """
    fields = ', '.join(ATTACHMENT_FIELDS)
    query = f"SELECT {fields} FROM Attachment {where_clause} ORDER BY ParentId, CreatedDate DESC"
    return query


def execute_soql_query_simple_salesforce(
    sf_client: Salesforce,
    query: str,
    error_handler: Optional[SalesforceErrorHandler] = None,
    usage_monitor: Optional[SalesforceUsageMonitor] = None
) -> List[Dict[str, Any]]:
    """
    Execute SOQL query using simple-salesforce and return raw records.

    Args:
        sf_client: Authenticated simple-salesforce client
        query: Complete SOQL query string
        error_handler: Optional error handler for retry logic
        usage_monitor: Optional usage monitor for tracking

    Returns:
        List of record dictionaries from Salesforce

    Raises:
        SFQueryError: If query execution fails
    """
    logger.debug("Executing SOQL query with simple-salesforce...")
    
    # Log query template details only once per execution
    global _query_logged
    with _query_logged_lock:
        if not _query_logged:
            logger.debug(f"Query length: {len(query)} chars")
            logger.debug(f"Query preview: {query[:150]}...")
            _query_logged = True
    
    # Always log execution progress
    logger.debug("Executing query batch")

    # Track API call start
    start_time = None
    if usage_monitor:
        start_time = usage_monitor.stats.last_call_time or 0

    try:
        # Execute query with retry logic if error handler provided
        if error_handler:
            def query_operation() -> Any:
                return sf_client.query_all(query)

            result = error_handler.execute_with_retry(query_operation)
        else:
            result = sf_client.query_all(query)

        # Track successful API call
        if usage_monitor:
            call_time = usage_monitor.stats.last_call_time or 0
            response_time = call_time - start_time if start_time else None
            usage_monitor.track_call('query', response_time, success=True)

        records = result['records']
        total_size = int(result['totalSize'])

        logger.info(f"Query successful: {total_size} records retrieved")

        return records

    except Exception as e:
        # Track failed API call
        if usage_monitor:
            call_time = usage_monitor.stats.last_call_time or 0
            response_time = call_time - start_time if start_time else None
            usage_monitor.track_call('query', response_time, success=False)

        logger.error(f"SOQL query failed: {e}")
        raise SFQueryError(f"SOQL query execution failed: {e}")


def _write_records_to_csv(records: List[Dict[str, Any]], output_file: Path) -> None:
    """
    Write query results to CSV file.

    Args:
        records: List of record dictionaries from simple-salesforce
        output_file: Path to output CSV file
    """
    if not records:
        _write_empty_csv(output_file)
        return

    # Get field names from first record (remove 'attributes' field added by SF)
    fieldnames = [field for field in records[0].keys() if field != 'attributes']

    with output_file.open('w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        # Write header
        writer.writeheader()

        # Write records (remove 'attributes' field)
        for record in records:
            clean_record = {k: v for k, v in record.items() if k != 'attributes'}
            writer.writerow(clean_record)


def _write_empty_csv(output_file: Path) -> None:
    """
    Create empty CSV file with proper headers.

    Args:
        output_file: Path to output CSV file
    """
    with output_file.open('w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(ATTACHMENT_FIELDS)


def _records_to_attachment_records(records: List[Dict[str, Any]]) -> List[AttachmentRecord]:
    """Convert raw Salesforce record dicts to AttachmentRecord instances."""
    result = []
    for record in records:
        result.append(AttachmentRecord(
            id=record.get('Id', ''),
            name=record.get('Name', ''),
            content_type=record.get('ContentType', ''),
            body_length=int(record.get('BodyLength', 0)),
            parent_id=record.get('ParentId', ''),
            created_date=record.get('CreatedDate', ''),
            last_modified_date=record.get('LastModifiedDate', ''),
            description=record.get('Description', '') or '',
        ))
    return result


def query_attachments_with_simple_salesforce(
    org_alias: str,
    where_clause: str,
    connection_pool: Optional[SalesforceConnectionPool] = None,
    error_handler: Optional[SalesforceErrorHandler] = None,
    usage_monitor: Optional[SalesforceUsageMonitor] = None,
    save_metadata: bool = False,
    metadata_csv_path: Optional[Path] = None,
) -> List[AttachmentRecord]:
    """
    Query Attachment records with WHERE clause filter using simple-salesforce.

    Returns in-memory AttachmentRecord list. Optionally writes CSV when
    save_metadata=True and metadata_csv_path is provided.

    Args:
        org_alias: Salesforce org alias
        where_clause: WHERE clause (e.g., "WHERE ParentId IN ('id1','id2')")
        connection_pool: Optional connection pool for client management
        error_handler: Optional error handler for retry logic
        usage_monitor: Optional usage monitor for tracking
        save_metadata: If True, write results to CSV
        metadata_csv_path: Path for metadata CSV (required when save_metadata=True)

    Returns:
        List of AttachmentRecord instances

    Raises:
        SFQueryError: If query fails
        SFAuthError: If authentication fails
    """
    # Build SOQL query
    query = build_attachment_query(where_clause)

    # Get client from pool or create new one
    if connection_pool:
        sf_client = connection_pool.get_connection()
        try:
            records = execute_soql_query_simple_salesforce(
                sf_client, query, error_handler, usage_monitor
            )
        finally:
            connection_pool.return_connection(sf_client)
    else:
        # Fallback: create client directly (for backward compatibility)
        from src.api.sf_auth_adapter import SFCLIAuthAdapter
        adapter = SFCLIAuthAdapter(org_alias)
        sf_client = adapter.get_client()

        records = execute_soql_query_simple_salesforce(
            sf_client, query, error_handler, usage_monitor
        )

    # Convert to AttachmentRecord instances
    attachment_records = _records_to_attachment_records(records)

    # Optionally write metadata CSV
    if save_metadata and metadata_csv_path:
        metadata_csv_path.parent.mkdir(parents=True, exist_ok=True)
        if records:
            _write_records_to_csv(records, metadata_csv_path)
        else:
            _write_empty_csv(metadata_csv_path)

    return attachment_records