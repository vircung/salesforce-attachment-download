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

from simple_salesforce import Salesforce

from src.api.sf_connection import SalesforceConnectionPool
from src.api.sf_error_handler import SalesforceErrorHandler
from src.api.usage_monitor import SalesforceUsageMonitor
from src.exceptions import SFQueryError, SFAuthError

logger = logging.getLogger(__name__)

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
    output_file: Path,
    error_handler: Optional[SalesforceErrorHandler] = None,
    usage_monitor: Optional[SalesforceUsageMonitor] = None
) -> int:
    """
    Execute SOQL query using simple-salesforce and save results to CSV.

    Args:
        sf_client: Authenticated simple-salesforce client
        query: Complete SOQL query string
        output_file: Path where CSV results will be saved
        error_handler: Optional error handler for retry logic
        usage_monitor: Optional usage monitor for tracking

    Returns:
        Number of records returned

    Raises:
        SFQueryError: If query execution fails
    """
    logger.debug("Executing SOQL query with simple-salesforce...")
    logger.debug(f"Query length: {len(query)} chars")
    logger.debug(f"Query preview: {query[:150]}...")

    # Ensure output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Track API call start
    start_time = None
    if usage_monitor:
        start_time = usage_monitor.stats.last_call_time or 0

    try:
        # Execute query with retry logic if error handler provided
        if error_handler:
            def query_operation():
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
        total_size = result['totalSize']

        logger.info(f"✓ Query successful: {total_size} records retrieved")

        # Write results to CSV
        if records:
            _write_records_to_csv(records, output_file)
        else:
            # Create empty CSV with headers
            _write_empty_csv(output_file)

        return total_size

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


def query_attachments_with_simple_salesforce(
    org_alias: str,
    output_dir: Path,
    where_clause: str,
    connection_pool: Optional[SalesforceConnectionPool] = None,
    error_handler: Optional[SalesforceErrorHandler] = None,
    usage_monitor: Optional[SalesforceUsageMonitor] = None
) -> Path:
    """
    Query Attachment records with WHERE clause filter using simple-salesforce.

    This function combines building the query, generating a timestamped filename,
    and executing the query using simple-salesforce instead of sf CLI.

    Args:
        org_alias: Salesforce org alias
        output_dir: Directory to save CSV file
        where_clause: WHERE clause (e.g., "WHERE ParentId IN ('id1','id2')")
        connection_pool: Optional connection pool for client management
        error_handler: Optional error handler for retry logic
        usage_monitor: Optional usage monitor for tracking

    Returns:
        Path to the generated CSV file

    Raises:
        SFQueryError: If query fails
        SFAuthError: If authentication fails
    """
    # Build SOQL query
    query = build_attachment_query(where_clause)

    # Generate timestamped filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = output_dir / f'attachments_{timestamp}.csv'

    # Get client from pool or create new one
    if connection_pool:
        sf_client = connection_pool.get_connection()
        try:
            record_count = execute_soql_query_simple_salesforce(
                sf_client, query, output_file, error_handler, usage_monitor
            )
            return output_file
        finally:
            connection_pool.return_connection(sf_client)
    else:
        # Fallback: create client directly (for backward compatibility)
        from src.api.sf_auth_adapter import SFCLIAuthAdapter
        adapter = SFCLIAuthAdapter(org_alias)
        sf_client = adapter.get_client()

        record_count = execute_soql_query_simple_salesforce(
            sf_client, query, output_file, error_handler, usage_monitor
        )
        return output_file