"""
SOQL Query Execution Module

Handles execution of SOQL queries via Salesforce CLI (sf data query).
This module replaces the bash script with native Python implementation.
"""

import subprocess
import logging
from pathlib import Path
from datetime import datetime
from typing import Literal

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


def execute_soql_query(
    org_alias: str,
    query: str,
    output_file: Path,
    result_format: Literal['csv', 'json'] = 'csv'
) -> Path:
    """
    Execute SOQL query using Salesforce CLI and save results to file.
    
    This function executes a SOQL query using 'sf data query' command
    and saves the output directly to a file. It includes intelligent
    error handling with helpful suggestions for common issues.
    
    Args:
        org_alias: Salesforce org alias from sf CLI authentication
        query: Complete SOQL query string
        output_file: Path where results will be saved
        result_format: Output format ('csv' or 'json')
    
    Returns:
        Path to the generated output file
    
    Raises:
        SFQueryError: If query execution fails with helpful error message
        SFAuthError: If authentication fails
        FileNotFoundError: If sf CLI is not installed
    
    Example:
        >>> query = "SELECT Id, Name FROM Account LIMIT 10"
        >>> output = Path('./accounts.csv')
        >>> execute_soql_query('my-org', query, output)
        Path('./accounts.csv')
    """
    logger.debug("Executing SOQL query via sf CLI...")
    logger.debug(f"Query length: {len(query)} chars")
    logger.debug(f"Query preview: {query[:150]}...")
    
    # Ensure output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Build sf CLI command
    cmd = [
        'sf', 'data', 'query',
        '--query', query,
        '--target-org', org_alias,
        '--result-format', result_format
    ]
    
    logger.debug(f"Executing: sf data query --target-org {org_alias} --result-format {result_format}")
    
    try:
        # Execute query
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes timeout
        )
        
        # Handle success
        if result.returncode == 0:
            # Write output to file
            output_file.write_text(result.stdout, encoding='utf-8')
            
            # Validate output
            _validate_output(output_file, result_format)
            
            # Count records and log success
            record_count = _count_records(output_file, result_format)
            logger.info(f"✓ Query successful: {record_count} records saved to {output_file.name}")
            
            return output_file
        
        # Handle failure with intelligent error messages
        _handle_query_error(result, query, org_alias)
        
    except subprocess.TimeoutExpired:
        raise SFQueryError(
            "Query execution timed out after 5 minutes.\n"
            "Possible causes:\n"
            "  - Query is too complex or returns too many records\n"
            "  - Network connection issues\n"
            "Suggestion: Try reducing --batch-size or adding more specific filters"
        )
    
    except FileNotFoundError:
        raise FileNotFoundError(
            "Salesforce CLI (sf) not found.\n"
            "Please install it: npm install -g @salesforce/cli\n"
            "Verify installation: sf --version"
        )
    
    except Exception as e:
        logger.error(f"Unexpected error during query execution: {e}")
        raise SFQueryError(f"Unexpected error: {e}")


def _validate_output(output_file: Path, result_format: str) -> None:
    """
    Validate that the output file was created and contains data.
    
    Args:
        output_file: Path to output file
        result_format: Expected format (csv or json)
    
    Raises:
        SFQueryError: If validation fails
    """
    if not output_file.exists():
        raise SFQueryError(
            "Query execution succeeded but output file was not created.\n"
            "This is unexpected. Please check sf CLI installation."
        )
    
    file_size = output_file.stat().st_size
    if file_size == 0:
        raise SFQueryError(
            "Query returned an empty file.\n"
            "This might indicate:\n"
            "  - No records match the query criteria\n"
            "  - An issue with sf CLI output formatting"
        )


def _count_records(output_file: Path, result_format: str) -> int:
    """
    Count the number of records in the output file.
    
    Args:
        output_file: Path to output file
        result_format: Format (csv or json)
    
    Returns:
        Number of records (excluding header for CSV)
    """
    if result_format == 'csv':
        lines = output_file.read_text(encoding='utf-8').splitlines()
        # CSV: first line is header, rest are records
        record_count = max(0, len(lines) - 1)
        return record_count
    else:
        # For JSON, we'd need to parse it - simplified for now
        return -1  # Unknown


def _handle_query_error(result: subprocess.CompletedProcess, query: str, org_alias: str) -> None:
    """
    Analyze error output and raise appropriate exception with helpful message.
    
    Args:
        result: Completed subprocess result
        query: Original SOQL query
        org_alias: Salesforce org alias
    
    Raises:
        SFQueryError: With intelligent error message
        SFAuthError: If authentication issue detected
    """
    stderr = result.stderr.lower() if result.stderr else ""
    stdout = result.stdout.lower() if result.stdout else ""
    combined_output = stderr + stdout
    
    # Authentication errors
    if any(phrase in combined_output for phrase in ['not authenticated', 'no authorization', 'invalid session']):
        raise SFAuthError(
            f"Authentication failed for org: {org_alias}\n"
            f"Please authenticate:\n"
            f"  sf org login web --alias {org_alias}\n"
            f"Or check existing auth:\n"
            f"  sf org display --target-org {org_alias}"
        )
    
    # Query length errors (SOQL has ~20k char limit)
    if any(phrase in combined_output for phrase in ['query length exceeded', 'string too long', 'query is too long']):
        raise SFQueryError(
            f"SOQL query exceeds Salesforce length limit (~20,000 chars).\n"
            f"Current query length: {len(query)} characters\n"
            f"\n"
            f"Solution: Reduce --batch-size to query fewer IDs per batch.\n"
            f"Try: --batch-size 50 (or even lower if needed)\n"
            f"\n"
            f"Technical note: Each 18-char Salesforce ID adds ~22 chars to the query:\n"
            f"  WHERE ParentId IN ('012345678901234ABC',...)  [quotes + comma + space]\n"
        )
    
    # Invalid WHERE clause
    if 'invalid' in combined_output and any(word in combined_output for word in ['where', 'clause', 'syntax']):
        # Extract first 100 chars of query for debugging
        query_preview = query[:100] + '...' if len(query) > 100 else query
        raise SFQueryError(
            f"Invalid SOQL query syntax.\n"
            f"Query preview: {query_preview}\n"
            f"\n"
            f"SF CLI Error:\n{result.stderr}\n"
            f"\n"
            f"Please check:\n"
            f"  - WHERE clause syntax\n"
            f"  - Salesforce ID format (18 characters)\n"
            f"  - Quote marks around IDs"
        )
    
    # Permission errors
    if any(phrase in combined_output for phrase in ['not accessible', 'insufficient access', 'permission']):
        raise SFQueryError(
            f"Insufficient permissions to query Attachment object.\n"
            f"\n"
            f"Required permissions:\n"
            f"  - Read access to Attachment object\n"
            f"  - View All Data (or specific object permissions)\n"
            f"\n"
            f"Contact your Salesforce administrator to grant access.\n"
            f"Current org: {org_alias}"
        )
    
    # Org not found
    if 'org' in combined_output and any(phrase in combined_output for phrase in ['not found', 'does not exist']):
        raise SFQueryError(
            f"Salesforce org not found: {org_alias}\n"
            f"\n"
            f"Available orgs:\n"
            f"  Run: sf org list\n"
            f"\n"
            f"To authenticate a new org:\n"
            f"  sf org login web --alias {org_alias}"
        )
    
    # Generic error
    error_details = result.stderr or result.stdout or "Unknown error"
    raise SFQueryError(
        f"SOQL query execution failed.\n"
        f"\n"
        f"Error details:\n{error_details}\n"
        f"\n"
        f"Query length: {len(query)} characters\n"
        f"Org: {org_alias}"
    )


def query_attachments_with_filter(
    org_alias: str,
    output_dir: Path,
    where_clause: str
) -> Path:
    """
    Query Attachment records with a WHERE clause filter and save to CSV.
    
    This is a convenience function that combines building the query,
    generating a timestamped filename, and executing the query.
    
    Args:
        org_alias: Salesforce org alias
        output_dir: Directory to save CSV file
        where_clause: WHERE clause (e.g., "WHERE ParentId IN ('id1','id2')")
    
    Returns:
        Path to the generated CSV file
    
    Raises:
        SFQueryError: If query fails
        SFAuthError: If authentication fails
    
    Example:
        >>> where = "WHERE ParentId IN ('001xxx', '002yyy')"
        >>> csv_path = query_attachments_with_filter('my-org', Path('./output'), where)
        >>> print(csv_path)
        Path('./output/attachments_20260114_143000.csv')
    """
    # Build SOQL query
    query = build_attachment_query(where_clause)
    
    # Generate timestamped filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = output_dir / f'attachments_{timestamp}.csv'
    
    # Execute query
    logger.debug(f"Querying attachments for org: {org_alias}")
    logger.debug(f"Filter: {where_clause[:100]}...")
    
    csv_path = execute_soql_query(
        org_alias=org_alias,
        query=query,
        output_file=output_file,
        result_format='csv'
    )
    
    return csv_path
