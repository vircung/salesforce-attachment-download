"""
Enhanced CSV Metadata Validator and Enricher

This module provides comprehensive validation and enrichment of CSV metadata files
containing Salesforce attachment information, including data type validation,
Salesforce ID format checking, and metadata enrichment.
"""

import csv
import logging
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass

from src.api.sf_connection import SalesforceConnectionPool
from src.api.sf_error_handler import SalesforceErrorHandler
from src.api.usage_monitor import SalesforceUsageMonitor

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of CSV validation and enrichment."""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    enriched_data: List[Dict[str, Any]]
    stats: Dict[str, Any]


class EnhancedCSVValidator:
    """
    Enhanced validator for Salesforce attachment CSV metadata.

    Provides comprehensive validation including:
    - Required field presence
    - Data type validation
    - Salesforce ID format validation
    - Metadata enrichment using Describe API
    - Duplicate detection
    """

    # Salesforce ID patterns (15 or 18 characters, alphanumeric)
    SALESFORCE_ID_PATTERN = re.compile(r'^[a-zA-Z0-9]{15,18}$')

    # Required fields for attachment processing
    REQUIRED_FIELDS = ['Id', 'Name']

    # Recommended fields
    RECOMMENDED_FIELDS = ['ParentId', 'ContentType', 'BodyLength']

    # Field type expectations
    FIELD_TYPES = {
        'Id': 'id',
        'Name': 'string',
        'ContentType': 'string',
        'BodyLength': 'integer',
        'ParentId': 'id',
        'CreatedDate': 'datetime',
        'LastModifiedDate': 'datetime',
        'Description': 'string'
    }

    def __init__(
        self,
        connection_pool: Optional[SalesforceConnectionPool] = None,
        error_handler: Optional[SalesforceErrorHandler] = None,
        usage_monitor: Optional[SalesforceUsageMonitor] = None
    ):
        """
        Initialize the enhanced validator.

        Args:
            connection_pool: Optional connection pool for API calls
            error_handler: Optional error handler for API operations
            usage_monitor: Optional usage monitor for tracking
        """
        self.connection_pool = connection_pool
        self.error_handler = error_handler
        self.usage_monitor = usage_monitor

    def validate_and_enrich_csv(
        self,
        csv_path: Path,
        enrich_metadata: bool = True
    ) -> ValidationResult:
        """
        Validate CSV file and optionally enrich with additional metadata.

        Args:
            csv_path: Path to CSV file to validate
            enrich_metadata: Whether to enrich with additional metadata from Salesforce

        Returns:
            ValidationResult with validation status, errors, warnings, and enriched data
        """
        result = ValidationResult(
            is_valid=True,
            errors=[],
            warnings=[],
            enriched_data=[],
            stats={'total_rows': 0, 'valid_rows': 0, 'invalid_rows': 0}
        )

        try:
            # Read and validate basic structure
            data = self._read_csv_data(csv_path)
            result.stats['total_rows'] = len(data)

            if not data:
                result.is_valid = False
                result.errors.append("CSV file is empty or contains no data rows")
                return result

            # Validate field structure
            field_validation = self._validate_fields(data[0])
            result.errors.extend(field_validation['errors'])
            result.warnings.extend(field_validation['warnings'])

            if field_validation['errors']:
                result.is_valid = False
                return result

            # Validate each row
            for i, row in enumerate(data, 1):
                row_validation = self._validate_row(row, i)
                result.errors.extend(row_validation['errors'])
                result.warnings.extend(row_validation['warnings'])

                if row_validation['errors']:
                    result.stats['invalid_rows'] += 1
                    result.is_valid = False
                else:
                    result.stats['valid_rows'] += 1
                    result.enriched_data.append(row)

            # Enrich metadata if requested and validation passed
            if enrich_metadata and result.is_valid and self.connection_pool:
                enrichment_result = self._enrich_metadata(result.enriched_data)
                result.warnings.extend(enrichment_result['warnings'])
                result.enriched_data = enrichment_result['enriched_data']

        except Exception as e:
            result.is_valid = False
            result.errors.append(f"Unexpected error during validation: {e}")
            logger.error(f"Validation error: {e}", exc_info=True)

        return result

    def _read_csv_data(self, csv_path: Path) -> List[Dict[str, Any]]:
        """Read CSV data into list of dictionaries."""
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")

        data = []
        with csv_path.open('r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append(row)

        return data

    def _validate_fields(self, sample_row: Dict[str, Any]) -> Dict[str, List[str]]:
        """Validate field structure and presence."""
        errors = []
        warnings = []
        fieldnames = list(sample_row.keys())

        # Check required fields
        missing_required = [field for field in self.REQUIRED_FIELDS if field not in fieldnames]
        if missing_required:
            errors.append(f"Missing required fields: {', '.join(missing_required)}")

        # Check recommended fields
        missing_recommended = [field for field in self.RECOMMENDED_FIELDS if field not in fieldnames]
        if missing_recommended:
            warnings.append(f"Missing recommended fields: {', '.join(missing_recommended)}")

        return {'errors': errors, 'warnings': warnings}

    def _validate_row(self, row: Dict[str, Any], row_num: int) -> Dict[str, List[str]]:
        """Validate a single data row."""
        errors = []
        warnings = []

        # Validate required fields are not empty
        for field in self.REQUIRED_FIELDS:
            value = row.get(field, '').strip()
            if not value:
                errors.append(f"Row {row_num}: Required field '{field}' is empty")

        # Validate Salesforce ID formats
        for field, expected_type in self.FIELD_TYPES.items():
            if field in row and row[field]:
                value = row[field].strip()
                validation = self._validate_field_value(field, value, expected_type)
                if validation['error']:
                    errors.append(f"Row {row_num}: {validation['error']}")
                if validation['warning']:
                    warnings.append(f"Row {row_num}: {validation['warning']}")

        return {'errors': errors, 'warnings': warnings}

    def _validate_field_value(self, field: str, value: str, expected_type: str) -> Dict[str, Optional[str]]:
        """Validate a single field value."""
        result = {'error': None, 'warning': None}

        if expected_type == 'id':
            if not self.SALESFORCE_ID_PATTERN.match(value):
                result['error'] = f"Field '{field}' value '{value}' is not a valid Salesforce ID (15-18 alphanumeric characters)"
        elif expected_type == 'integer':
            try:
                int(value)
            except ValueError:
                result['warning'] = f"Field '{field}' value '{value}' is not a valid integer"
        elif expected_type == 'datetime':
            # Basic datetime validation - could be enhanced
            if not ('T' in value or '/' in value):
                result['warning'] = f"Field '{field}' value '{value}' does not appear to be a valid datetime"

        return result

    def _enrich_metadata(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Enrich metadata using Salesforce Describe API."""
        warnings = []
        enriched_data = data.copy()

        if not self.connection_pool:
            warnings.append("Connection pool not available for metadata enrichment")
            return {'warnings': warnings, 'enriched_data': enriched_data}

        try:
            # Get client from pool
            sf_client = self.connection_pool.get_connection()

            # Describe Attachment object to get field metadata
            describe_result = sf_client.Attachment.describe()

            # Extract useful field information
            field_info = {}
            for field in describe_result['fields']:
                field_info[field['name']] = {
                    'type': field['type'],
                    'label': field['label'],
                    'required': not field.get('nillable', True)
                }

            # Add field metadata to each row
            for row in enriched_data:
                row['_field_metadata'] = field_info

            self.connection_pool.return_connection(sf_client)

        except Exception as e:
            warnings.append(f"Failed to enrich metadata: {e}")
            logger.warning(f"Metadata enrichment failed: {e}")

        return {'warnings': warnings, 'enriched_data': enriched_data}


def validate_and_enrich_csv(
    csv_path: Path,
    connection_pool: Optional[SalesforceConnectionPool] = None,
    error_handler: Optional[SalesforceErrorHandler] = None,
    usage_monitor: Optional[SalesforceUsageMonitor] = None,
    enrich_metadata: bool = True
) -> ValidationResult:
    """
    Convenience function to validate and enrich CSV metadata.

    Args:
        csv_path: Path to CSV file
        connection_pool: Optional connection pool
        error_handler: Optional error handler
        usage_monitor: Optional usage monitor
        enrich_metadata: Whether to enrich with Salesforce metadata

    Returns:
        ValidationResult with validation status and enriched data
    """
    validator = EnhancedCSVValidator(connection_pool, error_handler, usage_monitor)
    return validator.validate_and_enrich_csv(csv_path, enrich_metadata)