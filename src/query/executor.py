"""
Query Executor Module

Handles execution of SOQL queries for Attachment records.
"""

import logging
from pathlib import Path
from threading import Lock

from src.query.soql import query_attachments_with_filter

logger = logging.getLogger(__name__)

# Thread-safe flag to track if query template details have been logged
_query_logged_lock = Lock()
_query_logged = False


def run_query_script_with_filter(
    org_alias: str,
    output_dir: Path,
    where_clause: str
) -> Path:
    """
    Query attachments with a WHERE clause filter and save to CSV.

    This function is used by the CSV-records workflow to query attachments
    for specific ParentIds using a pre-built WHERE clause (e.g., WHERE ParentId IN (...)).

    This is now a thin wrapper around the native Python SOQL execution module.

    Args:
        org_alias: Salesforce org alias
        output_dir: Directory to save metadata CSV
        where_clause: Pre-built WHERE clause (e.g., "WHERE ParentId IN ('id1','id2')")

    Returns:
        Path to the generated CSV file

    Raises:
        SFQueryError: If query execution fails
        SFAuthError: If authentication fails
        FileNotFoundError: If sf CLI is not installed
    """
    logger.debug("Executing attachment query with filter...")
    
    # Log WHERE clause details only once per execution
    global _query_logged
    with _query_logged_lock:
        if not _query_logged:
            logger.debug(f"WHERE clause preview: {where_clause[:100]}...")
            _query_logged = True
    
    # Always log execution progress
    logger.debug("Executing query batch")
    
    # Execute query using native Python implementation
    csv_path = query_attachments_with_filter(
        org_alias=org_alias,
        output_dir=output_dir,
        where_clause=where_clause
    )

    return csv_path
