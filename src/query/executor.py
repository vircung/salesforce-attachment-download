"""
Query Executor Module

Handles execution of SOQL queries for Attachment records.
"""

import logging
from pathlib import Path

from src.query.soql import query_attachments_with_filter

logger = logging.getLogger(__name__)


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
    logger.info("Executing attachment query with filter...")
    logger.debug(f"WHERE clause preview: {where_clause[:100]}...")

    # Execute query using native Python implementation
    csv_path = query_attachments_with_filter(
        org_alias=org_alias,
        output_dir=output_dir,
        where_clause=where_clause
    )

    return csv_path
