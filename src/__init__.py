"""Salesforce Attachments Extract Package"""

# Expose key components at package level for convenience

# Exceptions (centralized)
from src.exceptions import SalesforceError, SFAuthError, SFAPIError

# API
from src.api.sf_auth import get_sf_auth_info
from src.api.sf_client import SalesforceClient

# Query
from src.query.filters import ParentIdFilter, apply_parent_id_filter, parse_filter_config
from src.query.executor import run_query_script, run_query_script_with_filter
from src.query.pagination import run_paginated_query

# CSV
from src.csv.processor import CsvRecordInfo, process_records_directory
from src.csv.validator import validate_metadata_csv

# Download
from src.download.downloader import download_attachments
from src.download.stats import DownloadStats
from src.download.filename import FilenameInfo, sanitize_filename, detect_filename_collisions
from src.download.metadata import read_metadata_csv

# Workflows
from src.workflows.csv_records import process_csv_records_workflow
from src.workflows.standard import process_standard_workflow

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
    # API
    "get_sf_auth_info",
    "SalesforceClient",
    # Query
    "ParentIdFilter",
    "apply_parent_id_filter",
    "parse_filter_config",
    "run_query_script",
    "run_query_script_with_filter",
    "run_paginated_query",
    # CSV
    "CsvRecordInfo",
    "process_records_directory",
    "validate_metadata_csv",
    # Download
    "download_attachments",
    "DownloadStats",
    "FilenameInfo",
    "sanitize_filename",
    "detect_filename_collisions",
    "read_metadata_csv",
    # Workflows
    "process_csv_records_workflow",
    "process_standard_workflow",
    # CLI
    "parse_arguments",
    # Utils
    "setup_logging",
    "log_section_header",
]
