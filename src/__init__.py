"""Salesforce Attachments Extract Package"""

# Expose key components at package level for convenience
from src.api.sf_auth import get_sf_auth_info, SFAuthError
from src.api.sf_client import SalesforceClient, SFAPIError

from src.query.filters import ParentIdFilter, apply_parent_id_filter, parse_filter_config
from src.query.executor import run_query_script, run_query_script_with_filter
from src.query.pagination import run_paginated_query

from src.csv.processor import CsvRecordInfo, process_records_directory
from src.csv.validator import validate_metadata_csv

from src.download.downloader import download_attachments, setup_logging

from src.workflows.csv_records import process_csv_records_workflow
from src.workflows.standard import process_standard_workflow

from src.cli.config import parse_arguments

__version__ = "0.2.0"
__all__ = [
    # API
    "get_sf_auth_info",
    "SFAuthError",
    "SalesforceClient",
    "SFAPIError",
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
    "setup_logging",
    # Workflows
    "process_csv_records_workflow",
    "process_standard_workflow",
    # CLI
    "parse_arguments",
]
