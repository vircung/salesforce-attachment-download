"""
Salesforce Field Discovery Module

This module provides dynamic field discovery using Salesforce Describe API,
allowing users to explore available fields on objects and validate field usage.
"""

import logging
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass

from simple_salesforce.api import Salesforce

from src.api.sf_connection import SalesforceConnectionPool
from src.api.sf_error_handler import SalesforceErrorHandler
from src.api.usage_monitor import SalesforceUsageMonitor

logger = logging.getLogger(__name__)


@dataclass
class FieldMetadata:
    """Metadata for a Salesforce object field."""
    name: str
    label: str
    type: str
    required: bool
    unique: bool
    length: Optional[int]
    precision: Optional[int]
    scale: Optional[int]
    picklist_values: List[str]
    reference_to: List[str]
    relationship_name: Optional[str]
    help_text: Optional[str]


@dataclass
class ObjectMetadata:
    """Metadata for a Salesforce object."""
    name: str
    label: str
    fields: Dict[str, FieldMetadata]
    key_prefix: Optional[str]
    custom: bool
    createable: bool
    updateable: bool
    deletable: bool
    queryable: bool


class SalesforceFieldDiscovery:
    """
    Field discovery service using Salesforce Describe API.

    Provides methods to discover object and field metadata, validate field usage,
    and suggest improvements for SOQL queries.
    """

    def __init__(
        self,
        connection_pool: Optional[SalesforceConnectionPool] = None,
        error_handler: Optional[SalesforceErrorHandler] = None,
        usage_monitor: Optional[SalesforceUsageMonitor] = None
    ):
        """
        Initialize field discovery service.

        Args:
            connection_pool: Optional connection pool for API calls
            error_handler: Optional error handler for API operations
            usage_monitor: Optional usage monitor for tracking
        """
        self.connection_pool = connection_pool
        self.error_handler = error_handler
        self.usage_monitor = usage_monitor
        self._cache: Dict[str, ObjectMetadata] = {}

    def discover_object_fields(
        self,
        object_name: str,
        use_cache: bool = True
    ) -> ObjectMetadata:
        """
        Discover all fields for a Salesforce object.

        Args:
            object_name: Name of the Salesforce object (e.g., 'Attachment', 'Account')
            use_cache: Whether to use cached results if available

        Returns:
            ObjectMetadata with field information

        Raises:
            Exception: If object discovery fails
        """
        if use_cache and object_name in self._cache:
            return self._cache[object_name]

        if not self.connection_pool:
            raise ValueError("Connection pool required for field discovery")

        # Track API call start
        start_time = None
        if self.usage_monitor:
            start_time = self.usage_monitor.stats.last_call_time or 0

        try:
            # Get client from pool
            sf_client = self.connection_pool.get_connection()

            # Execute describe operation
            def describe_operation():
                return sf_client.__getattr__(object_name).describe()

            if self.error_handler:
                describe_result = self.error_handler.execute_with_retry(describe_operation)
            else:
                describe_result = describe_operation()

            # Track successful API call
            if self.usage_monitor:
                call_time = self.usage_monitor.stats.last_call_time or 0
                response_time = call_time - start_time if start_time else None
                self.usage_monitor.track_call('describe', response_time, success=True)

            # Parse describe result
            metadata = self._parse_describe_result(object_name, describe_result)

            # Cache result
            self._cache[object_name] = metadata

            self.connection_pool.return_connection(sf_client)

            return metadata

        except Exception as e:
            # Track failed API call
            if self.usage_monitor:
                call_time = self.usage_monitor.stats.last_call_time or 0
                response_time = call_time - start_time if start_time else None
                self.usage_monitor.track_call('describe', response_time, success=False)

            logger.error(f"Field discovery failed for {object_name}: {e}")
            raise

    def _parse_describe_result(self, object_name: str, describe_result: Dict[str, Any]) -> ObjectMetadata:
        """Parse Salesforce describe API result into ObjectMetadata."""
        fields = {}

        for field_data in describe_result.get('fields', []):
            field_metadata = FieldMetadata(
                name=field_data['name'],
                label=field_data.get('label', field_data['name']),
                type=field_data['type'],
                required=not field_data.get('nillable', True),
                unique=field_data.get('unique', False),
                length=field_data.get('length'),
                precision=field_data.get('precision'),
                scale=field_data.get('scale'),
                picklist_values=[
                    pv['value'] for pv in field_data.get('picklistValues', [])
                    if pv.get('active', True)
                ],
                reference_to=field_data.get('referenceTo', []),
                relationship_name=field_data.get('relationshipName'),
                help_text=field_data.get('inlineHelpText')
            )
            fields[field_metadata.name] = field_metadata

        return ObjectMetadata(
            name=object_name,
            label=describe_result.get('label', object_name),
            fields=fields,
            key_prefix=describe_result.get('keyPrefix'),
            custom=describe_result.get('custom', False),
            createable=describe_result.get('createable', False),
            updateable=describe_result.get('updateable', False),
            deletable=describe_result.get('deletable', False),
            queryable=describe_result.get('queryable', False)
        )

    def validate_field_usage(
        self,
        object_name: str,
        field_names: List[str]
    ) -> Dict[str, Any]:
        """
        Validate that fields exist and are queryable on an object.

        Args:
            object_name: Salesforce object name
            field_names: List of field names to validate

        Returns:
            Dictionary with validation results:
            - valid_fields: List of valid field names
            - invalid_fields: List of invalid field names
            - suggestions: Suggested corrections for invalid fields
        """
        try:
            metadata = self.discover_object_fields(object_name)
        except Exception as e:
            return {
                'valid_fields': [],
                'invalid_fields': field_names,
                'suggestions': {},
                'error': str(e)
            }

        valid_fields = []
        invalid_fields = []
        suggestions = {}

        # Get all available field names (case-insensitive lookup)
        available_fields = {name.lower(): name for name in metadata.fields.keys()}

        for field_name in field_names:
            if field_name in metadata.fields:
                valid_fields.append(field_name)
            elif field_name.lower() in available_fields:
                # Case mismatch - suggest correct case
                correct_case = available_fields[field_name.lower()]
                valid_fields.append(correct_case)
                suggestions[field_name] = f"Use '{correct_case}' (correct case)"
            else:
                invalid_fields.append(field_name)
                # Find similar field names for suggestions
                similar = self._find_similar_fields(field_name, list(metadata.fields.keys()))
                if similar:
                    suggestions[field_name] = f"Did you mean '{similar}'?"

        return {
            'valid_fields': valid_fields,
            'invalid_fields': invalid_fields,
            'suggestions': suggestions,
            'object_metadata': {
                'name': metadata.name,
                'label': metadata.label,
                'total_fields': len(metadata.fields),
                'queryable': metadata.queryable
            }
        }

    def _find_similar_fields(self, target: str, candidates: List[str], max_suggestions: int = 3) -> Optional[str]:
        """Find similar field names using simple string similarity."""
        target_lower = target.lower()
        similarities = []

        for candidate in candidates:
            candidate_lower = candidate.lower()

            # Exact substring match
            if target_lower in candidate_lower or candidate_lower in target_lower:
                return candidate

            # Levenshtein distance approximation (simple version)
            if len(target) == len(candidate):
                distance = sum(1 for a, b in zip(target_lower, candidate_lower) if a != b)
                if distance <= 2:  # Allow up to 2 character differences
                    similarities.append((distance, candidate))

        if similarities:
            similarities.sort()
            return similarities[0][1]

        return None

    def get_queryable_fields(self, object_name: str) -> List[str]:
        """
        Get list of queryable fields for an object.

        Args:
            object_name: Salesforce object name

        Returns:
            List of field names that can be used in SOQL queries
        """
        try:
            metadata = self.discover_object_fields(object_name)
            return list(metadata.fields.keys())
        except Exception:
            return []

    def suggest_soql_improvements(
        self,
        object_name: str,
        current_fields: List[str]
    ) -> Dict[str, Any]:
        """
        Suggest improvements for SOQL queries based on field metadata.

        Args:
            current_fields: Currently selected fields
            object_name: Object being queried

        Returns:
            Dictionary with suggestions for query improvements
        """
        suggestions = {
            'missing_recommended_fields': [],
            'performance_tips': [],
            'field_type_notes': []
        }

        try:
            metadata = self.discover_object_fields(object_name)

            # Check for commonly useful fields that are missing
            recommended_missing = []
            recommended_fields = {'Id', 'Name', 'CreatedDate', 'LastModifiedDate'}

            for field in recommended_fields:
                if field in metadata.fields and field not in current_fields:
                    recommended_missing.append(field)

            if recommended_missing:
                suggestions['missing_recommended_fields'] = recommended_missing

            # Performance tips based on field types
            large_fields = []
            for field_name in current_fields:
                if field_name in metadata.fields:
                    field_meta = metadata.fields[field_name]
                    if field_meta.type in ('textarea', 'longtextarea') and field_meta.length and field_meta.length > 1000:
                        large_fields.append(field_name)

            if large_fields:
                suggestions['performance_tips'].append(
                    f"Consider removing large text fields from SELECT: {', '.join(large_fields)}"
                )

            # Field type information
            for field_name in current_fields:
                if field_name in metadata.fields:
                    field_meta = metadata.fields[field_name]
                    if field_meta.type == 'reference' and field_meta.relationship_name:
                        suggestions['field_type_notes'].append(
                            f"'{field_name}' is a lookup field - consider joining with {field_meta.relationship_name}"
                        )

        except Exception as e:
            suggestions['error'] = str(e)

        return suggestions

    def clear_cache(self) -> None:
        """Clear the metadata cache."""
        self._cache.clear()
        logger.info("Field discovery cache cleared")


def discover_fields(
    object_name: str,
    connection_pool: Optional[SalesforceConnectionPool] = None,
    error_handler: Optional[SalesforceErrorHandler] = None,
    usage_monitor: Optional[SalesforceUsageMonitor] = None
) -> ObjectMetadata:
    """
    Convenience function to discover object fields.

    Args:
        object_name: Salesforce object name
        connection_pool: Optional connection pool
        error_handler: Optional error handler
        usage_monitor: Optional usage monitor

    Returns:
        ObjectMetadata for the specified object
    """
    discovery = SalesforceFieldDiscovery(connection_pool, error_handler, usage_monitor)
    return discovery.discover_object_fields(object_name)