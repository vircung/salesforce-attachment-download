"""Salesforce Attachments Downloader Package"""

# Expose key components at package level for convenience

# Exceptions (centralized)
from src.exceptions import SalesforceError, SFAuthError, SFAPIError, SFQueryError

# API
from src.api.sf_auth import get_sf_auth_info

# Query
from src.query.filters import ParentIdFilter, apply_parent_id_filter, build_soql_where_clause
from src.query.soql import execute_soql_query, query_attachments_with_filter, build_attachment_query

# CSV
from src.constants import CsvRecordInfo
from src.csv.utils import process_records_directory
from src.csv.validator import validate_metadata_csv

# Download
# from src.download.downloader import download_attachments  # Removed to avoid circular import - import directly when needed
from src.download.stats import DownloadStats
from src.download.filename import FilenameInfo, sanitize_filename, detect_filename_collisions


# Workflows
# from src.workflows.orchestrator import process  # Removed to avoid circular import - import directly when needed

# CLI
from src.cli.config import parse_arguments

# Utils
from src.utils import setup_logging, log_section_header

__version__ = "0.2.0"
__all__ = [
    # Exceptions
    "SalesforceError",
    "SFAuthError",
    "SFAPIError",
    "SFQueryError",
    # API
    "get_sf_auth_info",
    # Query
    "ParentIdFilter",
    "apply_parent_id_filter",
    "build_soql_where_clause",
    "execute_soql_query",
    "query_attachments_with_filter",
    "build_attachment_query",
    # CSV
    "CsvRecordInfo",
    "process_records_directory",
    "validate_metadata_csv",
    # Download
    "DownloadStats",
    "FilenameInfo",
    "sanitize_filename",
    "detect_filename_collisions",

    # Workflows
    # "process",  # Removed to avoid circular import
    # CLI
    "parse_arguments",
    # Utils
    "setup_logging",
    "log_section_header",
]
