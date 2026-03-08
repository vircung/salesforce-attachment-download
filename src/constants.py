"""
Constants Module

Centralized constants for the application.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict


class WorkflowPhase:
    """Workflow phase identifiers and display names."""
    CSV_PROCESSING = "PHASE 1: CSV DISCOVERY & PROCESSING"
    SOQL_QUERYING = "PHASE 2: SOQL BATCH QUERYING"
    DOWNLOADS = "PHASE 3: DOWNLOAD ATTACHMENTS"
    SUMMARY = "WORKFLOW SUMMARY"


class Columns:
    """CSV column names."""
    ID = 'Id'
    PARENT_ID = 'ParentId'
    NAME = 'Name'
    CONTENT_TYPE = 'ContentType'
    BODY_LENGTH = 'BodyLength'


class ErrorMessages:
    """Standard error messages."""
    CHECK_SF_AUTH = "Please check your Salesforce CLI authentication (run: sf org list)"
    CHECK_QUERY_SYNTAX = "Check query syntax and record IDs"
    CHECK_NETWORK = "Check network connection and API access"


@dataclass
class CsvRecordInfo:
    """
    Information about a CSV file and its records.

    Attributes:
        csv_path: Path to the CSV file
        csv_name: Filename without extension (used for output directory)
        record_ids: List of extracted record IDs
        total_records: Total number of valid record IDs found
        id_batches: List of ID batches (each batch contains up to batch_size IDs)
        total_batches: Number of batches created
    """
    csv_path: Path
    csv_name: str
    record_ids: List[str]
    total_records: int
    id_batches: List[List[str]]
    total_batches: int

    def __str__(self) -> str:
        """String representation for logging."""
        return (
            f"CsvRecordInfo(csv_name='{self.csv_name}', "
            f"total_records={self.total_records}, "
            f"total_batches={self.total_batches})"
        )