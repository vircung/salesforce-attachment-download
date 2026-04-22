"""
Constants Module

Centralized constants for the application.
"""

from typing import Dict


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


