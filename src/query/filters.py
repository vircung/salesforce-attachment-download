"""
Attachment Filtering Module

Provides filtering logic for Salesforce Attachments based on ParentId.
Supports both prefix-based filtering (by object type) and exact ID matching.
"""

import logging
import re
from dataclasses import dataclass
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# Salesforce ID format: 15 or 18 characters, alphanumeric
SALESFORCE_ID_PATTERN = re.compile(r'^[a-zA-Z0-9]{15}$|^[a-zA-Z0-9]{18}$')
# Salesforce ID prefix: First 3 characters that identify object type
SALESFORCE_PREFIX_PATTERN = re.compile(r'^[a-zA-Z0-9]{3}$')


@dataclass
class ParentIdFilter:
    """
    Configuration for ParentId filtering.

    Attributes:
        prefixes: List of 3-character Salesforce ID prefixes to match
                  (e.g., ['aBo', '001'] for EMS_Attachment__c and Account)
        exact_ids: List of exact 15 or 18-character Salesforce IDs to match
    """
    prefixes: List[str]
    exact_ids: List[str]

    def __post_init__(self):
        """Validate filter configuration."""
        for prefix in self.prefixes:
            if not SALESFORCE_PREFIX_PATTERN.match(prefix):
                raise ValueError(
                    f"Invalid Salesforce ID prefix format: '{prefix}'. "
                    f"Expected 3 alphanumeric characters."
                )

        for sf_id in self.exact_ids:
            if not SALESFORCE_ID_PATTERN.match(sf_id):
                raise ValueError(
                    f"Invalid Salesforce ID format: '{sf_id}'. "
                    f"Expected 15 or 18 alphanumeric characters."
                )

    def has_filters(self) -> bool:
        """Check if any filters are configured."""
        return bool(self.prefixes or self.exact_ids)

    def __str__(self) -> str:
        """String representation for logging."""
        parts = []
        if self.prefixes:
            parts.append(f"prefixes={','.join(self.prefixes)}")
        if self.exact_ids:
            ids_preview = ','.join(self.exact_ids[:3])
            if len(self.exact_ids) > 3:
                ids_preview += f" (+{len(self.exact_ids) - 3} more)"
            parts.append(f"exact_ids={ids_preview}")
        return f"ParentIdFilter({', '.join(parts)})"


def build_soql_where_clause(filter_config: ParentIdFilter) -> str:
    """
    Build SOQL WHERE clause for ParentId filtering.

    Builds a SOQL WHERE clause for exact ParentId matching.

    Args:
        filter_config: Filter configuration with exact_ids

    Returns:
        SOQL WHERE clause string (e.g., "WHERE ParentId IN ('id1','id2')")
        Returns empty string if no exact_ids specified
    """
    if not filter_config or not filter_config.has_filters():
        return ""

    if not filter_config.exact_ids:
        return ""

    # Build WHERE IN clause with exact IDs
    # Escape single quotes in IDs (though Salesforce IDs shouldn't have them)
    escaped_ids = [id.replace("'", "\\'") for id in filter_config.exact_ids]
    ids_list = "','".join(escaped_ids)
    where_clause = f"WHERE ParentId IN ('{ids_list}')"
    
    logger.debug(f"Built SOQL WHERE clause with {len(filter_config.exact_ids)} IDs")

    return where_clause
